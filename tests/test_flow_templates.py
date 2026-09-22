"""Offline checks of shipped FlowTest XML; these do not execute Salesforce."""

import json
import re
import unittest
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement
from xml.parsers import expat
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "skills/sf-flow/assets/flowtests"
NS = "{http://soap.sforce.com/2006/04/metadata}"


def parse_xml(text):
    """Use Expat without DTDs/entities; ElementTree only stores constructed nodes."""
    if len(text.encode("utf-8")) > 100_000:
        raise ValueError("fixture too large")
    parser = expat.ParserCreate(namespace_separator="}")
    stack = []
    root = None

    def reject(*args):
        raise ValueError("DTD and entity declarations are forbidden")

    def start(name, attrs):
        nonlocal root
        tag = "{" + name if "}" in name else name
        element = SubElement(stack[-1], tag, attrs) if stack else Element(tag, attrs)
        if root is None:
            root = element
        stack.append(element)

    def data(value):
        if stack:
            stack[-1].text = (stack[-1].text or "") + value

    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.StartElementHandler = start
    parser.EndElementHandler = lambda name: stack.pop()
    parser.CharacterDataHandler = data
    parser.Parse(text, True)
    return root


def render(filename, substitutions):
    text = (ASSETS / filename).read_text(encoding="utf-8")
    for key, value in substitutions.items():
        text = text.replace("{{" + key + "}}", escape(str(value)))
    if re.search(r"\{\{[A-Z_]+\}\}", text):
        raise AssertionError("unmaterialized template")
    return parse_xml(text)


def children(node):
    return [child.tag.removeprefix(NS) for child in node]


class FlowTestTemplateTests(unittest.TestCase):
    def setUp(self):
        self.values = {
            "FLOW_API_NAME": "Fixture_Triage", "FLOW_VERSION": "7",
            "TEST_LABEL": 'Business <output> & "quoted"',
            "TRIGGER_RECORD_JSON": json.dumps({"attributes": {"type": "Task"},
                "Subject": 'Fixture <input> & "quoted"', "Priority": "Normal"}),
            "EXPECTED_RESOURCE": "$Record.Priority", "EXPECTED_VALUE": "High",
            "INPUT_VARIABLE": "requestText", "INPUT_VALUE": 'input <&> "quoted"',
        }

    def check_common(self, root):
        self.assertEqual(NS + "FlowTest", root.tag)
        self.assertEqual(["description", "flowApiName", "flowTestFlowVersions", "label",
                          "testPoints", "testPoints", "testType"], children(root))
        self.assertEqual("Fixture_Triage", root.findtext(NS + "flowApiName"))
        self.assertEqual("7", root.findtext(NS + "flowTestFlowVersions/" + NS + "flowVersionNumber"))
        self.assertEqual("WithAssertion", root.findtext(NS + "testType"))
        points = root.findall(NS + "testPoints")
        self.assertEqual(["Start", "Finish"], [p.findtext(NS + "elementApiName") for p in points])
        return points

    def test_record_fixture_is_one_typed_sobject_parameter(self):
        root = render("record-triggered-create.flowTest-meta.xml", self.values)
        start, finish = self.check_common(root)
        parameters = start.findall(NS + "parameters")
        self.assertEqual(1, len(parameters))
        parameter = parameters[0]
        self.assertEqual(["leftValueReference", "type", "value"], children(parameter))
        self.assertEqual("$Record", parameter.findtext(NS + "leftValueReference"))
        self.assertEqual("InputTriggeringRecordInitial", parameter.findtext(NS + "type"))
        fixture = json.loads(parameter.findtext(NS + "value/" + NS + "sobjectValue"))
        self.assertEqual(json.loads(self.values["TRIGGER_RECORD_JSON"]), fixture)
        self.assertEqual([], finish.findall(NS + "parameters"))

    def test_autolaunched_fixture_uses_named_input_variable(self):
        root = render("autolaunched-input.flowTest-meta.xml", {**self.values, "EXPECTED_RESOURCE": "resultText"})
        start, _ = self.check_common(root)
        parameter = start.find(NS + "parameters")
        self.assertEqual(["leftValueReference", "type", "value"], children(parameter))
        self.assertEqual("requestText", parameter.findtext(NS + "leftValueReference"))
        self.assertEqual("InputVariable", parameter.findtext(NS + "type"))
        self.assertEqual(self.values["INPUT_VALUE"], parameter.findtext(NS + "value/" + NS + "stringValue"))

    def test_assertions_detect_wrong_business_result_without_a_flow_fault(self):
        for filename in ("record-triggered-create.flowTest-meta.xml", "autolaunched-input.flowTest-meta.xml"):
            with self.subTest(filename=filename):
                expected_resource = "$Record.Priority" if filename.startswith("record-") else "resultText"
                root = render(filename, {**self.values, "EXPECTED_RESOURCE": expected_resource})
                _, finish = self.check_common(root)
                conditions = finish.findall(NS + "assertions/" + NS + "conditions")
                self.assertEqual(1, len(conditions))
                condition = conditions[0]
                resource = condition.findtext(NS + "leftValueReference")
                self.assertEqual(expected_resource, resource)
                self.assertEqual("EqualTo", condition.findtext(NS + "operator"))
                expected = condition.findtext(NS + "rightValue/" + NS + "stringValue")
                # Evaluate only this template's equality, never simulate Flow execution.
                self.assertEqual("High", expected)
                self.assertTrue({resource: "High", "$Flow.FaultMessage": None}[resource] == expected)
                self.assertFalse({resource: "Normal", "$Flow.FaultMessage": None}[resource] == expected)

    def test_xml_parser_rejects_external_and_internal_entity_definitions(self):
        for declaration in ('<!ENTITY x SYSTEM "file:///etc/passwd">', '<!ENTITY x "expanded">'):
            with self.subTest(declaration=declaration):
                with self.assertRaisesRegex(ValueError, "DTD and entity"):
                    parse_xml(f'<!DOCTYPE test [{declaration}]><test>&x;</test>')


if __name__ == "__main__":
    unittest.main()
