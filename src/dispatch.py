from collections import defaultdict

import sys
import argparse
from dataclasses import dataclass
from functools import singledispatch
import xml.dom.minidom as MD
from pathlib import Path
import json
from frozendict import frozendict

gko_directory = "../../ginkgo/document-create-functions/doc/doxygen/xml"
simple_directory = "doxygen/xml"


def constructor(self, payload):
    self.payload = payload


def create_class(name):
    return f"xml_{name}", type(f"xml_{name}", (object,), {"name": name,
                                                          "__init__": constructor})


classes = dict(create_class(name) for name in [
    "compounddef",
    "compoundname",
    "basecompoundref",
    "derivedcompoundref",
    "briefdescription",
    "detaileddescription",
    "sectiondef",
    "memberdef",
    "templateparamlist",
    "para",
    "ref",
    "computeroutput",
    "sp",
    "programlisting",
    "highlight",
    "codeline",
    "type",
    "definition",
    "name",
    "qualifiedname",
    "argsstring",
    "location",
    "innerclass",
    "innernamespace",
    "initializer",
    "formula",
    "simplesect",
    "parameterlist",
    "parametername",
    "itemizedlist",
    "orderedlist",
    "bold",
    "emphasis",
    "ulink",
    "ndash",
    "enumvalue",
    "templateparameterlist",
    # compounddef kinds
    "class",
    "struct",
    "union",
    "namespace",
    "group",
    "dir",
    "file"
])


@singledispatch
def dispatch(expr, ctx):
    raise AssertionError(f"Unhandled type {type(expr)}")


@dispatch.register
def dispatch_(expr: list, ctx):
    if len(expr) > 1:
        raise AssertionError(f"Node list has to have length of 1. Please handle iteration at caller site")
    if len(expr) == 0:
        return []
    else:
        return dispatch(expr[0], ctx)


@dispatch.register
def dispatch_(expr: MD.Element, ctx):
    return dispatch(classes[f"xml_{expr.tagName}"](expr), ctx)


def getElementsByTagName(node: MD.Element | MD.Document, tag):
    # This function is not recursive compared to Element.getElementsByTagName
    elements = []
    for child in node.childNodes:
        if isinstance(child, MD.Element) and child.tagName == tag:
            elements.append(child)
    return elements


@dispatch.register
def dispatch_(expr: classes['xml_group'] | classes["xml_dir"], ctx):
    print(f"Warning: encountered {expr.payload.attributes['kind'].value} documentation. This will be skipped!",
          file=sys.stderr)
    return None


@dispatch.register
def dispatch_(expr: classes["xml_class"] | classes["xml_struct"] | classes["xml_union"], ctx):
    # Find the class id ( used for files/html/etc )
    payload = expr.payload
    name = dispatch(getElementsByTagName(payload, 'compoundname'), ctx)
    data = {
        'type': payload.attributes['kind'].value,
        'id': payload.attributes['id'].value,
        'prot': payload.attributes['prot'].value,
        'name': name,
        'templateparameters': dispatch(getElementsByTagName(payload, 'templateparamlist'), ctx),
        'basecompoundref': [dispatch(d, ctx) for d in getElementsByTagName(payload, 'basecompoundref')],
        'derivedcompoundref': [dispatch(d, ctx) for d in getElementsByTagName(payload, 'derivedcompoundref')],
        'briefdescription': dispatch(getElementsByTagName(payload, 'briefdescription'), ctx),
        'detaileddescription': dispatch(getElementsByTagName(payload, 'detaileddescription'), ctx),
        'sectiondef': [dispatch(sec, ctx) for sec in getElementsByTagName(payload, 'sectiondef')],
        'innerclass': [dispatch(ic, ctx) for ic in getElementsByTagName(payload, 'innerclass')],
    }
    return data


@dispatch.register
def dispatch_(expr: classes['xml_compounddef'], ctx):
    kind = expr.payload.attributes['kind'].value
    return dispatch(classes[f"xml_{kind}"](expr.payload), ctx)


@dispatch.register
def dispatch_(expr: classes['xml_compoundname'], ctx):
    return dispatch(expr.payload.childNodes[0], ctx)


@dispatch.register
def dispatch_(expr: classes['xml_basecompoundref'] | classes['xml_derivedcompoundref'], ctx):
    return dispatch(expr.payload.childNodes[0], ctx)


@dispatch.register
def dispatch_(expr: classes['xml_briefdescription'] | classes['xml_detaileddescription'], ctx):
    para = getElementsByTagName(expr.payload, 'para')
    if para:
        return sum([dispatch(p, ctx) for p in para], start=[])
    else:
        return [""]


@dispatch.register
def dispatch_(expr: classes['xml_sectiondef'], ctx):
    return {
        'type': expr.payload.attributes['kind'].value,
        'members': [dispatch(member, ctx) for member in getElementsByTagName(expr.payload, "memberdef")]
    }


@dispatch.register
def dispatch_(expr: classes['xml_memberdef'], ctx):
    payload = expr.payload
    kind = payload.attributes["kind"].value
    base_data = {
        'type': 'member',
        **dict(payload.attributes.items()),
        'name': dispatch(getElementsByTagName(payload, 'name'), ctx),
        'briefdescription': dispatch(getElementsByTagName(payload, 'briefdescription'), ctx),
        'detaileddescription': dispatch(getElementsByTagName(payload, 'detaileddescription'), ctx),
        # ignore inbodydescription since that doesn't exist in C++
        'location': dispatch(getElementsByTagName(payload, 'location'), ctx)
    }

    if kind == 'variable':
        initializer = getElementsByTagName(payload, 'initializer')
        data = {
            **base_data,
            'definition': dispatch(getElementsByTagName(payload, 'definition'), ctx),
            'initializer': dispatch(initializer, ctx) if initializer else "",
        }
    elif kind == 'function':
        data = {
            **base_data,
            'templateparameters': dispatch(getElementsByTagName(payload, 'templateparamlist'), ctx),
            'definition': dispatch(getElementsByTagName(payload, 'definition'), ctx),
            'return_type': dispatch(getElementsByTagName(payload, 'type'), ctx),
            'argsstring': dispatch(getElementsByTagName(payload, 'argsstring'), ctx),
        }
    elif kind == 'enum':
        data = {
            **base_data,
            # @todo: need qualified name?
            'items': [dispatch(item, ctx) for item in getElementsByTagName(payload, 'enumvalue')]
        }
    elif kind == 'typedef':
        data = {
            **base_data,
            'base_type': dispatch(getElementsByTagName(payload, 'type'), ctx),
            'templateparameters': dispatch(getElementsByTagName(payload, 'templateparamlist'), ctx)
        }
    elif kind == 'friend':
        data = {
            **base_data,
            'name': f"{dispatch(getElementsByTagName(payload, 'type'), ctx)} {base_data['name']}"
        }
    elif kind == 'define':  # macros
        data = base_data
    else:
        raise AssertionError(f"Encountered unexpected member kind: {kind}")
    return data


@dispatch.register
def dispatch_(expr: classes['xml_namespace'] | classes['xml_file'], ctx):
    payload = expr.payload
    data = {
        'type': payload.attributes['kind'].value,
        'id': payload.attributes['id'].value,
        'name': dispatch(getElementsByTagName(payload, 'compoundname'), ctx),
        'innerclass': [dispatch(ic, ctx) for ic in getElementsByTagName(payload, 'innerclass')],
        'innernamespace': [dispatch(nn, ctx) for nn in getElementsByTagName(payload, 'innernamespace')],
        'briefdescription': dispatch(getElementsByTagName(payload, 'briefdescription'), ctx),
        'detaileddescription': dispatch(getElementsByTagName(payload, 'detaileddescription'), ctx),
        'sectiondef': [dispatch(sec, ctx) for sec in getElementsByTagName(payload, 'sectiondef')]
    }
    return data


@dispatch.register
def dispatch_(expr: classes['xml_innerclass'] | classes['xml_innernamespace'], ctx):
    return {
        **dict(expr.payload.attributes.items()),
        'name': dispatch(expr.payload.childNodes[0], ctx)
    }


@dispatch.register
def dispatch_(expr: classes['xml_templateparamlist'], ctx):
    def dispatch_item(item):
        _type = dispatch(getElementsByTagName(item, 'type'), ctx)
        if declname := getElementsByTagName(item, 'declname'):
            defname = getElementsByTagName(item, 'defname')
            if dispatch(declname[0].childNodes[0], ctx) != dispatch(defname[0].childNodes[0], ctx):
                raise AssertionError(
                    f"Can't handle mismatched declaration and definition names: {declname}, {defname}.")
            _type += dispatch(declname[0].childNodes, ctx)
        return " ".join(_type)

    return [
        dispatch_item(item) for item in getElementsByTagName(expr.payload, 'param')
    ]


@dispatch.register
def dispatch_(expr: classes['xml_enumvalue'], ctx):
    return {
        'type': 'enumvalue',
        'name': dispatch(getElementsByTagName(expr.payload, 'name'), ctx),
        'briefdescription': dispatch(getElementsByTagName(expr.payload, 'briefdescription'), ctx),
        'detaileddescription': dispatch(getElementsByTagName(expr.payload, 'detaileddescription'), ctx)
    }


@dispatch.register
def dispatch_(expr: classes['xml_name'] | classes['xml_qualifiedname'] | classes['xml_definition'] | classes[
    'xml_parametername'], ctx):
    return dispatch(expr.payload.childNodes[0], ctx)


@dispatch.register
def dispatch_(expr: classes['xml_type'], ctx):
    if children := expr.payload.childNodes:
        return [dispatch(child, ctx) for child in children]
    else:
        return ["void"]


@dispatch.register
def dispatch_(expr: classes['xml_argsstring'] | classes['xml_initializer'], ctx):
    if expr.payload.childNodes:
        return dispatch(expr.payload.childNodes[0], ctx)
    else:
        return ""


@dispatch.register
def dispatch_(expr: classes['xml_location'], ctx):
    return {
        'type': 'location',
        **dict(expr.payload.attributes.items())
    }


@dispatch.register
def dispatch_(expr: classes['xml_para'], ctx):
    data = []
    for child in expr.payload.childNodes:
        child_data = dispatch(child, ctx)
        if isinstance(child_data, str):
            child_data = child_data.strip()
        if child_data:
            data.append(child_data)
    return data


@dispatch.register
def dispatch_(expr: classes['xml_bold'] | classes["xml_emphasis"], ctx):
    return {
        'type': 'markup',
        'kind': expr.payload.tagName,
        'body': dispatch(expr.payload.childNodes[0], ctx)
    }


@dispatch.register
def dispatch_(expr: classes['xml_ndash'], ctx):
    return "--"


@dispatch.register
def dispatch_(expr: classes['xml_ulink'], ctx):
    return {
        'type': 'hyperlink',
        'url': expr.payload.attributes["url"].value,
        'body': dispatch(expr.payload.childNodes[0], ctx)
    }


@dispatch.register
def dispatch_(expr: classes['xml_itemizedlist'] | classes["xml_orderedlist"], ctx):
    return {
        'type': expr.payload.tagName,
        'items': [dispatch(getElementsByTagName(item, 'para'), ctx) for item in
                  getElementsByTagName(expr.payload, "listitem")]
    }


@dispatch.register
def dispatch_(expr: classes['xml_ref'], ctx):
    return {
        'type': 'reference',
        'name': dispatch(expr.payload.childNodes[0], ctx),
        'refid': expr.payload.attributes['refid'].value
    }


@dispatch.register
def dispatch_(expr: classes['xml_simplesect'], ctx):
    return {
        'type': 'simplesect',
        'kind': expr.payload.attributes['kind'].value,
        'body': dispatch(expr.payload.childNodes[0], ctx)
    }


@dispatch.register
def dispatch_(expr: classes['xml_parameterlist'], ctx):
    def dispatch_item(item):
        return {
            'type': 'parameter',
            'name': dispatch(getElementsByTagName(getElementsByTagName(item, 'parameternamelist')[0],
                                                  'parametername'), ctx),
            'description': dispatch(getElementsByTagName(getElementsByTagName(item, 'parameterdescription')[0],
                                                         'para'), ctx),
        }

    return [
        dispatch_item(item) for item in getElementsByTagName(expr.payload, 'parameteritem')
    ]


@dispatch.register
def dispatch_(expr: classes['xml_computeroutput'], ctx):
    return {
        'type': 'inline_code',
        'code': dispatch(expr.payload.childNodes[0], ctx)
    }


@dispatch.register
def dispatch_(expr: classes['xml_sp'], ctx):
    return " "


@dispatch.register
def dispatch_(expr: classes['xml_programlisting'], ctx):
    first_cl = getElementsByTagName(expr.payload, 'codeline')[0]
    if first_cl is None:
        style = 'text'
        start_idx = 0
    else:
        style = dispatch(first_cl, ctx).strip(" {}")
        start_idx = 1

    return {'type': 'block_code',
            'style': style,
            'code': "\n".join(dispatch(cl, ctx) for cl in getElementsByTagName(expr.payload, 'codeline')[start_idx:])}


@dispatch.register
def dispatch_(expr: classes['xml_highlight'], ctx):
    # @todo: maybe handle highlighting?
    def sanitize(fragment):
        # let sphinx handle references
        match fragment:
            case {"name": name}:
                return name
            case str(body):
                return body
            case _:
                raise AssertionError(f"Can't reduce fragment to str: {fragment}")

    return "".join(
        sanitize(dispatch(child, ctx)) for child in expr.payload.childNodes
    )


@dispatch.register
def dispatch_(expr: classes['xml_codeline'], ctx):
    return "".join(
        dispatch(child, ctx) for child in expr.payload.childNodes
    )


@dispatch.register
def dispatch_(expr: classes['xml_formula'], ctx):
    code = expr.payload.childNodes[0].data
    if code.startswith("\\[") and code.endswith("\\]"):
        return {
            'type': 'block_math',
            'code': code.strip("\[] ")
        }
    elif code.startswith("$") and code.endswith("$"):
        return {
            'type': 'inline_math',
            'code': code.strip("$ ")
        }
    else:
        raise AssertionError(f"Unrecognized math formula: {code}")


@dispatch.register
def dispatch_(expr: MD.Text, ctx):
    stripped_text = expr.data.strip()
    return stripped_text


@dispatch.register
def dispatch_(expr: MD.Document, ctx):
    return dispatch(getElementsByTagName(getElementsByTagName(expr, "doxygen")[0], "compounddef"), ctx)


def dispatch_index(expr: MD.Document, ctx):
    data = dict(
        classes=dict(),
        namespaces=dict(),
        globals=dict()
    )

    index = getElementsByTagName(expr, 'doxygenindex')[0]

    map_kind = {"class": "classes", "struct": "classes", "union": "classes",
                "namespace": "namespaces", "file": "globals"}
    for compoud in getElementsByTagName(index, 'compound'):
        file = f"{ctx.directory}/{compoud.attributes['refid'].value}.xml"
        kind = compoud.attributes['kind'].value
        new_data = dispatch(MD.parse(file), ctx)
        if new_data and kind != "file":
            data[map_kind[kind]][new_data["id"]] = new_data
        if new_data and kind == "file":
            innerclasses = new_data.pop('innerclass')
            innernamespaces = new_data.pop('innernamespace')
            sections = new_data.pop('sectiondef')
            contains = innernamespaces + innerclasses
            for sec in sections:
                striped_section = []
                for member in sec['members']:
                    striped_section.append({
                        'refid': member['id'],
                        'prot': member['prot'],
                        'name': member['name']
                    })
                contains += striped_section

            data[map_kind[kind]][new_data["id"]] = {**new_data, 'contains': contains}

            for sec in sections:
                for member in sec['members']:
                    data[map_kind[kind]][member["id"]] = member

    return data


def add_extra_context(data):
    def visit_classes(visitor, data_):
        match data_:
            case {"type": "class", **kwargs} | {"type": "struct", **kwargs}:
                visitor(data_)
                visit_classes(visitor, kwargs)
            case [*args]:
                [visit_classes(visitor, d) for d in args]
            case {**kwargs}:
                [visit_classes(visitor, v) for _, v in kwargs.items()]
            case _:
                pass

    all_classes = dict()

    def gather_all_classes(data_):
        all_classes[data_["name"]] = data_["id"]

    visit_classes(gather_all_classes, data)

    specializations = defaultdict(set)
    specializationof = defaultdict(dict)
    innerclass_of = defaultdict(dict)

    def gather_extra_data(data_):
        def remove_specialization(name):
            return name.partition('<')[0]

        name = data_["name"]
        id = data_["id"]

        base_name = remove_specialization(name)
        if name != base_name:
            specializations[base_name].add(frozendict(name=name, id=id))
            specializationof[name] = base_name

        innerclasses = data_["innerclass"]
        for ic in innerclasses:
            innerclass_of[ic["name"]] = dict(name=name, id=id)

    visit_classes(gather_extra_data, data)

    def transform(data_):
        match data_:
            case {"type": "class", **kwargs} | {"type": "struct", **kwargs}:
                name = kwargs["name"]
                return {
                    "type": data_["type"],
                    **transform(kwargs),
                    "specializations": list(specializations[name]),
                    "specializationof": specializationof[name],
                    "innerclassof": innerclass_of[name]
                }
            case [*args]:
                return [transform(d) for d in args]
            case {**kwargs}:
                return {k: transform(v) for k, v in kwargs.items()}
            case _:
                return data_

    return transform(data)


@dataclass
class Context(object):
    directory: str


xml_directory = simple_directory

parser = arg_parse.ArgumentParser(
    description = "Translates doxygen xml output into a more sensible format"
);

parser.add_argument('-d', '--doxygen',
    required = False,
    default  = xml_directory,
    help     = "Path to the doxygen generated xml directory"
);

args = parser.parse_args();

index = Path(xml_directory) / "index.xml"
dom = MD.parse(str(index.resolve()))

parsed = dispatch_index(dom, Context(directory=xml_directory))

print(json.dumps(parsed, indent=2))
