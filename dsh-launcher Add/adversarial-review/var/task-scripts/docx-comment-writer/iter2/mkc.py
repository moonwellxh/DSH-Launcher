# -*- coding: utf-8 -*-
"""L0 helper: build minimal docx packages from body XML fragments.

role : deterministic fixture builder for integration probes
in   : body xml string, options
out  : .docx on disk
rerun: imported by other probes
"""
import os
import zipfile

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

CT = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''

ROOT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''

DOC_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>'''

NSALL = (
    'xmlns:w="%s" '
    'xmlns:r="%s" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'xmlns:v="urn:schemas-microsoft-com:vml" '
    'xmlns:w10="urn:schemas-microsoft-com:office:word" '
    'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"'
) % (W, R)


def doc_xml(body):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:document %s><w:body>%s'
            '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
            '</w:body></w:document>' % (NSALL, body))


def build(path, body, with_rels=True, extra=None, extra_ct=None, rels=None):
    extra = extra or {}
    body_xml = body if body.lstrip().startswith('<?xml') else doc_xml(body)
    ct = CT
    if extra_ct:
        ct = ct.replace('</Types>', extra_ct + '</Types>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ct)
        z.writestr('_rels/.rels', ROOT_RELS)
        z.writestr('word/document.xml', body_xml)
        if with_rels:
            z.writestr('word/_rels/document.xml.rels', rels or DOC_RELS)
        for name, data in extra.items():
            z.writestr(name, data)
    return path


if __name__ == '__main__':
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work')
    os.makedirs(out, exist_ok=True)
    p = build(os.path.join(out, 'smoke.docx'),
              '<w:p><w:r><w:t>HELLO</w:t></w:r></w:p>')
    print(p)
