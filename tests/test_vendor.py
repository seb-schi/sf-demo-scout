"""Hermetic tests for the maintainer-only skill vendoring entrypoint."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "vendor-skills.sh"
REVISION = "8febf3f2bfb537a7586f36ee42dcf5e5d69c02a5"
YAML_IMPORT_ROOT = Path(yaml.__file__).resolve().parent.parent


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode())
        if path.is_symlink():
            digest.update(b"L")
            digest.update(os.readlink(path).encode())
        elif path.is_dir():
            digest.update(b"D")
        else:
            digest.update(b"F")
            digest.update(path.read_bytes())
    return digest.hexdigest()


class VendorFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.plugin = root / "plugin"
        self.skills = self.plugin / "skills"
        self.source = root / "upstream"
        self.bin = root / "bin"
        self.git_log = root / "git.log"
        (self.plugin / "scripts").mkdir(parents=True)
        self.skills.mkdir()
        self.source.mkdir()
        self.bin.mkdir()
        shutil.copy2(SCRIPT, self.plugin / "scripts" / "vendor-skills.sh")
        os.symlink(sys.executable, self.bin / "python3")
        self._write_fake_git()

    def _write_fake_git(self) -> None:
        fake_git = self.bin / "git"
        fake_git.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import os
                from pathlib import Path
                import shutil
                import sys

                args = sys.argv[1:]
                log = Path(os.environ["VENDOR_TEST_GIT_LOG"])
                with log.open("a") as stream:
                    stream.write(" ".join(args) + "\\n")
                if args and args[0] == "clone":
                    if os.environ.get("VENDOR_TEST_CLONE_FAIL") == "1":
                        sys.exit(31)
                    destination = Path(args[-1])
                    shutil.copytree(
                        Path(os.environ["VENDOR_TEST_SOURCE"]),
                        destination,
                        symlinks=True,
                    )
                    sys.exit(0)
                if "rev-parse" in args:
                    print(os.environ["VENDOR_TEST_REVISION"])
                    sys.exit(0)
                if "fetch" in args or "checkout" in args:
                    sys.exit(0)
                print("unsupported fake git invocation: " + " ".join(args), file=sys.stderr)
                sys.exit(32)
                """
            )
        )
        fake_git.chmod(0o755)

    def add_upstream_skill(self, name: str = "demo") -> Path:
        skill = self.source / "skills" / name
        (skill / "nested").mkdir(parents=True)
        (skill / "SKILL.md").write_text("# upstream skill\n")
        (skill / ".hidden").write_text("hidden\n")
        (skill / "nested" / "data.txt").write_text("nested\n")
        return skill

    def add_old_skill(self, name: str = "demo") -> Path:
        skill = self.skills / name
        skill.mkdir()
        (skill / "SKILL.md").write_text("# old skill\n")
        (skill / "obsolete.txt").write_text("must disappear after success\n")
        return skill

    def write_manifest(self, skills: list[dict], sources: dict | None = None) -> None:
        manifest = {
            "sources": sources
            or {
                "fixture": {
                    "repo": "https://example.invalid/fixture.git",
                    "type": "clone",
                    "branch": "main",
                    "revision": REVISION,
                }
            },
            "skills": skills,
        }
        (self.plugin / "skills-manifest.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False)
        )

    def run(self, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env.update(
            {
                "PATH": f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin",
                "PYTHONDONTWRITEBYTECODE": "1",
                "VENDOR_TEST_GIT_LOG": str(self.git_log),
                "VENDOR_TEST_SOURCE": str(self.source),
                "VENDOR_TEST_REVISION": REVISION,
            }
        )
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["/bin/bash", str(self.plugin / "scripts" / "vendor-skills.sh")],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )

    def install_failure_injector(self) -> Path:
        injector = self.root / "injector"
        injector.mkdir()
        (injector / "sitecustomize.py").write_text(
            textwrap.dedent(
                """\
                import os
                from pathlib import Path
                import shutil

                _copytree = shutil.copytree
                _rmtree = shutil.rmtree
                _replace = os.replace

                def copytree(source, destination, *args, **kwargs):
                    if (os.environ.get("VENDOR_TEST_COPY_FAIL") == "1"
                            and ".stage-" in str(destination)):
                        raise OSError("injected staged copy failure")
                    return _copytree(source, destination, *args, **kwargs)

                def replace(source, destination, *args, **kwargs):
                    source_path = Path(source)
                    destination_path = Path(destination)
                    if (os.environ.get("VENDOR_TEST_PUBLISH_FAIL") == "1"
                            and source_path.name == "new"
                            and destination_path.name == "demo"):
                        raise OSError("injected publish failure")
                    if (os.environ.get("VENDOR_TEST_RESTORE_FAIL") == "1"
                            and source_path.name.startswith(".demo.backup-")
                            and destination_path.name == "demo"):
                        raise OSError("injected restore failure")
                    result = _replace(source, destination, *args, **kwargs)
                    if (os.environ.get("VENDOR_TEST_POST_PUBLISH_SIGNAL") == "1"
                            and source_path.name == "new"
                            and destination_path.name == "demo"):
                        import signal
                        os.kill(os.getpid(), signal.SIGTERM)
                    return result

                def rmtree(path, *args, **kwargs):
                    path = Path(path)
                    if path.name.startswith(".demo.backup-"):
                        mode = os.environ.get("VENDOR_TEST_BACKUP_CLEANUP")
                        if mode == "error":
                            raise OSError("injected backup cleanup failure")
                        if mode == "signal":
                            import signal
                            os.kill(os.getpid(), signal.SIGTERM)
                        if mode == "partial":
                            (path / "obsolete.txt").unlink()
                            raise OSError("injected partial backup cleanup failure")
                    return _rmtree(path, *args, **kwargs)

                shutil.copytree = copytree
                shutil.rmtree = rmtree
                os.replace = replace
                """
            )
        )
        return injector

    def failure_env(self, injector: Path, **values: str) -> dict[str, str]:
        """Expose only the injector and the parent interpreter's PyYAML root."""
        environment = {
            "PYTHONPATH": os.pathsep.join((str(injector), str(YAML_IMPORT_ROOT)))
        }
        environment.update(values)
        return environment


class VendorSkillsTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], VendorFixture]:
        temporary = tempfile.TemporaryDirectory()
        return temporary, VendorFixture(Path(temporary.name))

    def test_replace_copies_complete_tree_and_removes_obsolete_files(self) -> None:
        temporary, fixture = self.fixture()
        self.addCleanup(temporary.cleanup)
        fixture.add_upstream_skill()
        fixture.add_old_skill()
        fixture.write_manifest(
            [{"name": "demo", "source": "fixture", "path": "skills/demo", "policy": "replace"}]
        )

        result = fixture.run()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((fixture.skills / "demo" / "SKILL.md").read_text(), "# upstream skill\n")
        self.assertEqual((fixture.skills / "demo" / ".hidden").read_text(), "hidden\n")
        self.assertEqual((fixture.skills / "demo" / "nested" / "data.txt").read_text(), "nested\n")
        self.assertFalse((fixture.skills / "demo" / "obsolete.txt").exists())
        self.assertIn("VENDORED_COUNT=1", result.stdout)
        self.assertIn("FAILED_COUNT=0", result.stdout)
        self.assertIn(REVISION, result.stdout)
        self.assertIn("skills/demo", result.stdout)

    def test_real_local_git_checkout_uses_pinned_revision_after_branch_advances(self) -> None:
        temporary, fixture = self.fixture()
        self.addCleanup(temporary.cleanup)
        git = shutil.which("git")
        if git is None:
            self.fail("git prerequisite missing")
        repository = fixture.root / "real-upstream"
        repository.mkdir()
        git_config = fixture.root / "empty-gitconfig"
        git_config.write_text("")
        git_env = os.environ.copy()
        git_env.update(
            {
                "GIT_CONFIG_GLOBAL": str(git_config),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
            }
        )

        def run_git(*arguments: str) -> str:
            result = subprocess.run(
                [git, *arguments],
                env=git_env,
                text=True,
                capture_output=True,
                check=False,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

        run_git("init", "--quiet", "--initial-branch=main", str(repository))
        skill = repository / "skills" / "demo"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# pinned bytes\n")
        run_git("-C", str(repository), "add", ".")
        run_git(
            "-C",
            str(repository),
            "-c",
            "user.name=Vendoring Test",
            "-c",
            "user.email=vendor@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "pinned",
        )
        pinned_revision = run_git("-C", str(repository), "rev-parse", "HEAD")
        (skill / "SKILL.md").write_text("# moving branch bytes\n")
        (skill / "branch-only.txt").write_text("must not be installed\n")
        run_git("-C", str(repository), "add", ".")
        run_git(
            "-C",
            str(repository),
            "-c",
            "user.name=Vendoring Test",
            "-c",
            "user.email=vendor@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "branch advanced",
        )
        advanced_revision = run_git("-C", str(repository), "rev-parse", "HEAD")
        self.assertNotEqual(pinned_revision, advanced_revision)

        fixture.add_old_skill()
        fixture.write_manifest(
            [{"name": "demo", "source": "fixture", "path": "skills/demo", "policy": "replace"}],
            {
                "fixture": {
                    "repo": repository.as_uri(),
                    "type": "clone",
                    "branch": "main",
                    "revision": pinned_revision,
                }
            },
        )
        real_bin = fixture.root / "real-bin"
        real_bin.mkdir()
        os.symlink(sys.executable, real_bin / "python3")

        result = fixture.run(
            {
                "PATH": f"{real_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
                "GIT_CONFIG_GLOBAL": str(git_config),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        installed = fixture.skills / "demo"
        self.assertEqual((installed / "SKILL.md").read_text(), "# pinned bytes\n")
        self.assertFalse((installed / "branch-only.txt").exists())
        self.assertIn("revision=" + pinned_revision, result.stdout)
        self.assertNotIn("revision=" + advanced_revision, result.stdout)

    def test_adapted_and_frozen_policies_are_visible_skips_without_clone(self) -> None:
        temporary, fixture = self.fixture()
        self.addCleanup(temporary.cleanup)
        adapted = fixture.add_old_skill("adapted")
        frozen = fixture.add_old_skill("frozen")
        fixture.write_manifest(
            [
                {
                    "name": "adapted",
                    "source": "fixture",
                    "path": "skills/adapted",
                    "policy": "adapted",
                    "reason": "keeps local cross references",
                },
                {
                    "name": "frozen",
                    "policy": "frozen",
                    "reason": "requires an unavailable public tool",
                },
            ]
        )
        before = (tree_digest(adapted), tree_digest(frozen))

        result = fixture.run()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, (tree_digest(adapted), tree_digest(frozen)))
        self.assertIn("ADAPTED_COUNT=1", result.stdout)
        self.assertIn("FROZEN_COUNT=1", result.stdout)
        self.assertIn("keeps local cross references", result.stdout)
        self.assertIn("requires an unavailable public tool", result.stdout)
        self.assertFalse(fixture.git_log.exists())

    def test_manifest_is_fully_validated_before_clone_or_skill_mutation(self) -> None:
        invalid_skills = [
            ([{"name": "demo", "source": "fixture", "path": "skills/demo"}], "missing policy"),
            ([{"name": "../demo", "source": "fixture", "path": "skills/demo", "policy": "replace"}], "unsafe name"),
            ([{"name": "demo", "source": "fixture", "path": "../escape", "policy": "replace"}], "unsafe path"),
            ([{"name": "demo", "source": "fixture", "path": ".", "policy": "replace"}], "dot path"),
            ([{"name": "demo", "source": "fixture", "path": "skills/demo", "policy": "mystery"}], "unknown policy"),
            ([{"name": "demo", "source": "fixture", "path": "skills/demo", "policy": []}], "non-string policy"),
            ([{"name": "demo", "policy": "adapted", "reason": ""}], "missing protected reason"),
        ]
        for skills, label in invalid_skills:
            with self.subTest(label=label):
                temporary, fixture = self.fixture()
                self.addCleanup(temporary.cleanup)
                old = fixture.add_old_skill()
                before = tree_digest(old)
                fixture.write_manifest(skills)
                result = fixture.run()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(tree_digest(old), before)
                self.assertFalse(fixture.git_log.exists())
                self.assertNotIn("Traceback", result.stderr)

    def test_rejects_malformed_manifest_and_non_full_revision(self) -> None:
        cases = ("skills: [", "short-revision")
        for case in cases:
            with self.subTest(case=case):
                temporary, fixture = self.fixture()
                self.addCleanup(temporary.cleanup)
                old = fixture.add_old_skill()
                before = tree_digest(old)
                if case == "skills: [":
                    (fixture.plugin / "skills-manifest.yaml").write_text(case)
                else:
                    fixture.write_manifest(
                        [{"name": "demo", "source": "fixture", "path": "skills/demo", "policy": "replace"}],
                        {
                            "fixture": {
                                "repo": "https://example.invalid/fixture.git",
                                "type": "clone",
                                "revision": "8febf3f",
                            }
                        },
                    )
                result = fixture.run()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(tree_digest(old), before)
                self.assertFalse(fixture.git_log.exists())

    def test_clone_failure_leaves_exact_old_tree(self) -> None:
        temporary, fixture = self.fixture()
        self.addCleanup(temporary.cleanup)
        fixture.add_upstream_skill()
        old = fixture.add_old_skill()
        fixture.write_manifest(
            [{"name": "demo", "source": "fixture", "path": "skills/demo", "policy": "replace"}]
        )
        before = tree_digest(old)

        result = fixture.run({"VENDOR_TEST_CLONE_FAIL": "1"})

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(tree_digest(old), before)
        self.assertIn("FAILED_COUNT=1", result.stdout)

    def test_staged_copy_failure_leaves_exact_old_tree(self) -> None:
        temporary, fixture = self.fixture()
        self.addCleanup(temporary.cleanup)
        fixture.add_upstream_skill()
        old = fixture.add_old_skill()
        fixture.write_manifest(
            [{"name": "demo", "source": "fixture", "path": "skills/demo", "policy": "replace"}]
        )
        before = tree_digest(old)
        injector = fixture.install_failure_injector()

        result = fixture.run(
            fixture.failure_env(injector, VENDOR_TEST_COPY_FAIL="1")
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(tree_digest(old), before)
        self.assertIn("FAILED_COUNT=1", result.stdout)

    def test_publish_failure_restores_exact_old_tree(self) -> None:
        temporary, fixture = self.fixture()
        self.addCleanup(temporary.cleanup)
        fixture.add_upstream_skill()
        old = fixture.add_old_skill()
        fixture.write_manifest(
            [{"name": "demo", "source": "fixture", "path": "skills/demo", "policy": "replace"}]
        )
        before = tree_digest(old)
        injector = fixture.install_failure_injector()

        result = fixture.run(
            fixture.failure_env(injector, VENDOR_TEST_PUBLISH_FAIL="1")
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old.is_dir())
        self.assertEqual(tree_digest(old), before)
        self.assertIn("restored previous tree", result.stdout)

    def test_restore_failure_preserves_backup_and_prints_recovery_path(self) -> None:
        temporary, fixture = self.fixture()
        self.addCleanup(temporary.cleanup)
        fixture.add_upstream_skill()
        old = fixture.add_old_skill()
        fixture.write_manifest(
            [{"name": "demo", "source": "fixture", "path": "skills/demo", "policy": "replace"}]
        )
        before = tree_digest(old)
        injector = fixture.install_failure_injector()

        result = fixture.run(
            fixture.failure_env(
                injector,
                VENDOR_TEST_PUBLISH_FAIL="1",
                VENDOR_TEST_RESTORE_FAIL="1",
            )
        )

        self.assertNotEqual(result.returncode, 0)
        backups = list(fixture.skills.glob(".demo.backup-*"))
        self.assertEqual(len(backups), 1, result.stdout + result.stderr)
        self.assertEqual(tree_digest(backups[0]), before)
        self.assertIn(str(backups[0]), result.stdout + result.stderr)
        self.assertIn("RECOVERY_PATH=", result.stdout + result.stderr)

    def test_backup_cleanup_failure_keeps_installed_tree_and_reports_partial_result(self) -> None:
        for mode in ("error", "signal", "partial"):
            with self.subTest(mode=mode):
                temporary, fixture = self.fixture()
                self.addCleanup(temporary.cleanup)
                fixture.add_upstream_skill()
                old = fixture.add_old_skill()
                fixture.write_manifest(
                    [{"name": "demo", "source": "fixture", "path": "skills/demo", "policy": "replace"}]
                )
                before = tree_digest(old)
                injector = fixture.install_failure_injector()

                result = fixture.run(
                    fixture.failure_env(
                        injector, VENDOR_TEST_BACKUP_CLEANUP=mode
                    )
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(
                    (fixture.skills / "demo" / "SKILL.md").read_text(),
                    "# upstream skill\n",
                )
                backups = list(fixture.skills.glob(".demo.backup-*"))
                self.assertEqual(len(backups), 1, result.stdout + result.stderr)
                if mode == "partial":
                    self.assertNotEqual(tree_digest(backups[0]), before)
                else:
                    self.assertEqual(tree_digest(backups[0]), before)
                self.assertIn("BACKUP_PATH=" + str(backups[0]), result.stdout + result.stderr)
                self.assertIn("VENDORED_COUNT=1", result.stdout)
                self.assertIn("FAILED_COUNT=1", result.stdout)

    def test_signal_after_publish_counts_install_and_retains_old_backup(self) -> None:
        temporary, fixture = self.fixture()
        self.addCleanup(temporary.cleanup)
        fixture.add_upstream_skill()
        old = fixture.add_old_skill()
        fixture.write_manifest(
            [{"name": "demo", "source": "fixture", "path": "skills/demo", "policy": "replace"}]
        )
        before = tree_digest(old)
        injector = fixture.install_failure_injector()

        result = fixture.run(
            fixture.failure_env(
                injector, VENDOR_TEST_POST_PUBLISH_SIGNAL="1"
            )
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            (fixture.skills / "demo" / "SKILL.md").read_text(),
            "# upstream skill\n",
        )
        backups = list(fixture.skills.glob(".demo.backup-*"))
        self.assertEqual(len(backups), 1, result.stdout + result.stderr)
        self.assertEqual(tree_digest(backups[0]), before)
        self.assertIn("BACKUP_PATH=" + str(backups[0]), result.stdout + result.stderr)
        self.assertIn("VENDORED_COUNT=1", result.stdout)
        self.assertIn("FAILED_COUNT=1", result.stdout)
        self.assertNotIn("RECOVERY_PATH=", result.stdout + result.stderr)

    def test_existing_lock_fails_without_mutation_or_stale_lock_deletion(self) -> None:
        temporary, fixture = self.fixture()
        self.addCleanup(temporary.cleanup)
        fixture.add_upstream_skill()
        old = fixture.add_old_skill()
        fixture.write_manifest(
            [{"name": "demo", "source": "fixture", "path": "skills/demo", "policy": "replace"}]
        )
        before = tree_digest(old)
        lock = fixture.plugin / ".vendor-skills.lock"
        lock.mkdir()
        (lock / "owner").write_text("someone else\n")

        result = fixture.run()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(tree_digest(old), before)
        self.assertTrue(lock.is_dir())
        self.assertFalse(fixture.git_log.exists())

    def test_source_and_target_symlink_escapes_are_rejected(self) -> None:
        for location in ("source", "target"):
            with self.subTest(location=location):
                temporary, fixture = self.fixture()
                self.addCleanup(temporary.cleanup)
                outside = fixture.root / "outside"
                outside.mkdir()
                (outside / "SKILL.md").write_text("# outside\n")
                if location == "source":
                    (fixture.source / "skills").mkdir()
                    os.symlink(outside, fixture.source / "skills" / "demo")
                    old = fixture.add_old_skill()
                else:
                    fixture.add_upstream_skill()
                    os.symlink(outside, fixture.skills / "demo")
                    old = outside
                before = tree_digest(old)
                fixture.write_manifest(
                    [{"name": "demo", "source": "fixture", "path": "skills/demo", "policy": "replace"}]
                )
                result = fixture.run()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(tree_digest(old), before)

    def test_manifest_has_the_reviewed_policy_roster(self) -> None:
        manifest = yaml.safe_load((REPO_ROOT / "skills-manifest.yaml").read_text())
        actual = {skill["name"]: skill["policy"] for skill in manifest["skills"]}
        replace = {
            "platform-custom-field-generate",
            "platform-permission-set-generate",
            "agentforce-test",
            "agentforce-observe",
            "platform-soql-query",
            "platform-apex-logs-debug",
            "platform-validation-rule-generate",
            "platform-list-view-generate",
            "platform-value-set-generate",
            "platform-custom-report-type-generate",
            "platform-report-generate",
            "platform-custom-setting-generate",
            "platform-custom-metadata-type-generate",
        }
        adapted = {
            "platform-custom-object-generate",
            "platform-sharing-rules-generate",
            "agentforce-generate",
            "service-email-to-case-configure",
            "experience-lwc-generate",
            "platform-apex-test-run",
            "platform-data-manage",
            "platform-metadata-deploy",
            "dx-code-analyzer-run",
            "platform-apex-generate",
            "platform-apex-test-generate",
        }
        frozen = {"sf-flow", "platform-flexipage-generate"}
        expected = {
            **{name: "replace" for name in replace},
            **{name: "adapted" for name in adapted},
            **{name: "frozen" for name in frozen},
        }
        self.assertEqual(actual, expected)
        protected = [skill for skill in manifest["skills"] if skill["policy"] != "replace"]
        self.assertTrue(all(skill.get("reason", "").strip() for skill in protected))


if __name__ == "__main__":
    unittest.main()
