"""One value edit, preserving every other byte; bounded, DTD-free XML parsing."""
from dataclasses import dataclass, field
from xml.parsers import expat
from xml.sax.saxutils import escape

LIMIT = 2 * 1024 * 1024
Q = "http://soap.sforce.com/2006/04/metadata}"


class RepairError(ValueError):
    pass


@dataclass
class Node:
    name: str
    attrs: dict
    start: int
    end: int = 0
    content: list = field(default_factory=list)
    markup: bool = False

    def children(self, name):
        return [n for n in self.content if isinstance(n, Node) and n.name == Q + name]

    def value(self):
        if any(isinstance(n, Node) for n in self.content):
            raise RepairError("nested scalar XML is unsupported")
        return "".join(self.content)


def xml(content, root_name):
    if len(content) > LIMIT:
        raise RepairError("XML exceeds the repair limit")
    content.decode("utf-8")  # byte offsets below require UTF-8, not UTF-16
    parser = expat.ParserCreate(encoding="UTF-8", namespace_separator="}")
    stack, roots = [], []
    count = 0

    def reject(*_):
        raise RepairError("DTD, entities and processing instructions are unsupported")

    def declaration(version, encoding, standalone):
        if version != "1.0" or (encoding and encoding.lower() not in ("utf-8", "utf8", "us-ascii")):
            raise RepairError("only UTF-8 XML 1.0 is supported")

    def start(name, attrs):
        nonlocal count
        count += 1
        if len(stack) >= 64 or count > 20000:
            raise RepairError("XML nesting or element limit exceeded")
        node = Node(name, attrs, parser.CurrentByteIndex)
        (stack[-1].content if stack else roots).append(node)
        stack.append(node)

    def end(_):
        stack.pop().end = parser.CurrentByteIndex

    def characters(value):
        if stack:
            if stack[-1].content and isinstance(stack[-1].content[-1], str):
                stack[-1].content[-1] += value
            else:
                stack[-1].content.append(value)

    def markup(*_):
        if stack:
            stack[-1].markup = True

    # Explicit user-requested stdlib parser: reject DOCTYPE at its opening,
    # disable parameter entities, and reject external references before resolution.
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    parser.ProcessingInstructionHandler = reject
    parser.XmlDeclHandler = declaration
    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.CharacterDataHandler = characters
    parser.CommentHandler = parser.StartCdataSectionHandler = markup
    try:
        parser.Parse(content, True)
    except expat.ExpatError as error:
        raise RepairError("invalid report/folder XML") from error
    if len(roots) != 1 or roots[0].name != Q + root_name:
        raise RepairError("unexpected XML root")
    return roots[0]


def signature(node):
    # Formatting and comments are not Salesforce metadata; every actual element,
    # attribute and scalar value remains part of the acceptance comparison.
    has_children = any(isinstance(n, Node) for n in node.content)
    content = tuple(signature(n) if isinstance(n, Node) else n
                    for n in node.content if isinstance(n, Node) or not has_children or n.strip())
    return node.name, sorted(node.attrs.items()), content


def selected_value(root, column, operator):
    filters = root.children("filter")
    if len(filters) != 1 or root.children("block"):
        raise RepairError("only one top-level filter on a non-joined report is supported")
    matches = []
    for item in filters[0].children("criteriaItems"):
        columns, operators = item.children("column"), item.children("operator")
        if len(columns) != 1 or len(operators) != 1:
            raise RepairError("ambiguous report criterion")
        if columns[0].value() == column and operators[0].value() == operator:
            values = item.children("value")
            if len(values) != 1 or values[0].attrs or values[0].markup:
                raise RepairError("unsupported scalar filter value")
            values[0].value()
            matches.append(values[0])
    if len(matches) != 1:
        raise RepairError("filter predicate is absent or ambiguous")
    return matches[0]


def candidate(content, delta):
    value = selected_value(xml(content, "Report"), delta["column"], delta["operator"])
    existing = value.value()
    if existing not in (delta["before"], delta["after"]):
        raise RepairError("filter value conflicts with the requested before-state")
    if existing == delta["after"]:
        return content, True
    start = content.index(b">", value.start) + 1  # scalar has no attributes
    encoded = escape(delta["after"], {"\r": "&#13;"}).encode("utf-8")
    if content[start - 2:start] == b"/>":
        tag = content[value.start + 1:start - 2].strip()
        output = content[:value.start] + b"<" + tag + b">" + encoded + b"</" + tag + b">" + content[start:]
    else:
        output = content[:start] + encoded + content[value.end:]
    selected_value(xml(output, "Report"), delta["column"], delta["operator"]).value()
    return output, False
