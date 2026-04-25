#!/usr/bin/env python3
"""
scan_ear.py
-----------
Scans a WebLogic split-directory EAR project built with Ant and outputs
scan-output.yaml to the project root.

Run from the project root:
    python3 .github/skills/generate-context/scan_ear.py

Uses only the Python standard library — no pip installs required.
"""

import os
import re
import glob
import sys
from xml.etree import ElementTree as ET
from datetime import datetime, timezone


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def find_file(*patterns):
    """Return the first file matching any of the given glob patterns."""
    for pattern in patterns:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return matches[0]
    return None


def parse_xml(path):
    """Parse an XML file, stripping namespaces. Returns root element or None."""
    if not path or not os.path.exists(path):
        return None
    try:
        content = open(path, encoding='utf-8', errors='replace').read()
        # Strip namespace declarations so ElementTree tag matching stays simple
        content = re.sub(r'\sxmlns(?::\w+)?="[^"]+"', '', content)
        content = re.sub(r'<\w+:', '<', content)
        content = re.sub(r'</\w+:', '</', content)
        return ET.fromstring(content)
    except Exception as e:
        return None


def find_all(root, tag):
    """Find all descendant elements with the given tag."""
    if root is None:
        return []
    return root.findall(f'.//{tag}')


def text_of(root, tag):
    """Return stripped text of the first matching descendant, or None."""
    if root is None:
        return None
    elem = root.find(f'.//{tag}')
    return elem.text.strip() if elem is not None and elem.text else None


def read_file(path):
    """Read a file safely, returning empty string on failure."""
    try:
        return open(path, encoding='utf-8', errors='replace').read()
    except Exception:
        return ''


# ─────────────────────────────────────────────────────────────────────────────
# Output builder
# ─────────────────────────────────────────────────────────────────────────────

lines = []
warnings = []


def section(name):
    lines.append('')
    lines.append(f'{name}:')


def field(key, value, indent=1):
    pad = '  ' * indent
    if isinstance(value, bool):
        lines.append(f'{pad}{key}: {str(value).lower()}')
    elif value is None:
        lines.append(f'{pad}{key}: null')
    else:
        # Escape quotes in string values
        safe = str(value).replace('"', '\\"')
        lines.append(f'{pad}{key}: "{safe}"')


def raw(text):
    lines.append(text)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Build info
# ─────────────────────────────────────────────────────────────────────────────

section('build')

if os.path.exists('build.xml'):
    content = read_file('build.xml')
    src_match = re.search(r'source="([^"]+)"', content)
    tgt_match = re.search(r'target="([^"]+)"', content)

    field('build_tool', 'ant')
    field('java_source', src_match.group(1) if src_match else 'unknown')
    field('java_target', tgt_match.group(1) if tgt_match else 'unknown')

    wl_version = None
    if os.path.exists('build.properties'):
        props = read_file('build.properties')
        m = re.search(r'(?:weblogic|wl|server)\.version\s*=\s*(.+)', props, re.I)
        if m:
            wl_version = m.group(1).strip()
    field('weblogic_version', wl_version or 'check build.properties')
else:
    field('build_tool', 'not_found')
    warnings.append('build.xml not found in project root')


# ─────────────────────────────────────────────────────────────────────────────
# 2. EAR modules (application.xml)
# ─────────────────────────────────────────────────────────────────────────────

section('modules')

app_xml_path = find_file(
    '**/ear/META-INF/application.xml',
    '**/META-INF/application.xml',
)

if app_xml_path:
    root = parse_xml(app_xml_path)
    found_any = False

    for ejb_elem in find_all(root, 'ejb'):
        if ejb_elem.text and ejb_elem.text.strip():
            raw(f'  - name: "{ejb_elem.text.strip()}"')
            raw(f'    type: ejb')
            found_any = True

    for web_elem in find_all(root, 'web-uri'):
        if web_elem.text and web_elem.text.strip():
            raw(f'  - name: "{web_elem.text.strip()}"')
            raw(f'    type: war')
            found_any = True

    if not found_any:
        raw('  []')
        warnings.append('application.xml found but no modules detected')
else:
    raw('  []')
    warnings.append('application.xml not found')


# ─────────────────────────────────────────────────────────────────────────────
# 3. EJB layer
# ─────────────────────────────────────────────────────────────────────────────

section('ejb_layer')

ejb_jar_path = find_file('**/META-INF/ejb-jar.xml')
wl_ejb_path  = find_file('**/META-INF/weblogic-ejb-jar.xml')

if ejb_jar_path:
    ejb_root = parse_xml(ejb_jar_path)
    wl_root  = parse_xml(wl_ejb_path) if wl_ejb_path else None

    # Session beans
    raw('  session_beans:')
    session_names = []
    for sb in find_all(ejb_root, 'session'):
        name = text_of(sb, 'ejb-name')
        if name:
            raw(f'    - "{name}"')
            session_names.append(name)
    if not session_names:
        raw('    []')

    # MDB beans — cross-reference with weblogic-ejb-jar.xml for queue details
    raw('  message_driven_beans:')
    mdb_found = False

    for mdb in find_all(ejb_root, 'message-driven'):
        name = text_of(mdb, 'ejb-name')
        if not name:
            continue

        mdb_found = True
        raw(f'  - name: "{name}"')

        if wl_root:
            # Find matching weblogic-enterprise-bean entry
            for wb in find_all(wl_root, 'weblogic-enterprise-bean'):
                wl_name = text_of(wb, 'ejb-name')
                if wl_name and wl_name.strip() == name:
                    queue = text_of(wb, 'destination-jndi-name')
                    cf    = text_of(wb, 'connection-factory-jndi-name')
                    pool  = text_of(wb, 'max-beans-in-free-pool')
                    if queue: raw(f'    queue_jndi: "{queue}"')
                    if cf:    raw(f'    connection_factory: "{cf}"')
                    if pool:  raw(f'    max_pool_size: "{pool}"')
                    break

    if not mdb_found:
        raw('    []')

else:
    raw('  session_beans: []')
    raw('  message_driven_beans: []')
    warnings.append('ejb-jar.xml not found')


# ─────────────────────────────────────────────────────────────────────────────
# 4. Database
# ─────────────────────────────────────────────────────────────────────────────

section('database')

wl_app_path   = find_file('**/META-INF/weblogic-application.xml')
persistence_p = find_file('**/persistence.xml')

if wl_app_path:
    wl_app_root = parse_xml(wl_app_path)
    ds = text_of(wl_app_root, 'data-source-name')
    field('datasource_jndi', ds or 'not found in weblogic-application.xml')
else:
    field('datasource_jndi', 'weblogic-application.xml not found')
    warnings.append('weblogic-application.xml not found')

if persistence_p:
    content = read_file(persistence_p)
    m = re.search(r'hibernate\.dialect[^>]*?value="([^"]+)"', content, re.I)
    if not m:
        m = re.search(r'<property\s+name="hibernate\.dialect"\s+value="([^"]+)"',
                      content, re.I)
    field('orm', 'jpa')
    field('dialect', m.group(1) if m else 'not specified')
else:
    field('orm', 'unknown')
    field('dialect', 'persistence.xml not found')


# ─────────────────────────────────────────────────────────────────────────────
# 5. Web layer
# ─────────────────────────────────────────────────────────────────────────────

section('web_layer')

web_xml_path = find_file('**/WEB-INF/web.xml')
app_ctx_path = find_file('**/WEB-INF/applicationContext.xml',
                          '**/WEB-INF/app-context.xml',
                          '**/applicationContext.xml')

if web_xml_path:
    content = read_file(web_xml_path)
    field('spring_mvc',  'DispatcherServlet' in content)
    field('jsp_present', '.jsp' in content)
else:
    field('spring_mvc',  False)
    field('jsp_present', False)
    warnings.append('web.xml not found')

if app_ctx_path:
    content = read_file(app_ctx_path).lower()
    field('thymeleaf', 'thymeleafviewresolver' in content or 'thymeleaf' in content)
else:
    field('thymeleaf', False)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Special libraries (lib/ JAR scan)
# ─────────────────────────────────────────────────────────────────────────────

section('special_libs')

lib_dirs = glob.glob('**/lib', recursive=True)
lib_dir  = lib_dirs[0] if lib_dirs else None

LIB_PATTERNS = {
    'hapi_hl7':      ['hapi-*.jar', 'hapi*.jar'],
    'symphonia_hl7': ['symphonia*.jar'],
    'apache_fop':    ['fop*.jar', 'fop-*.jar'],
    'itext':         ['itext*.jar', 'itextpdf*.jar'],
    'drools':        ['drools*.jar', 'kie-api*.jar'],
    'oracle_jdbc':   ['ojdbc*.jar'],
    'spring':        ['spring-core*.jar'],
    'jackson':       ['jackson-databind*.jar'],
    'activemq':      ['activemq*.jar'],
}

if lib_dir:
    for lib_name, patterns in LIB_PATTERNS.items():
        found_jar = None
        for pat in patterns:
            matches = glob.glob(os.path.join(lib_dir, pat))
            if matches:
                found_jar = os.path.basename(matches[0])
                break

        if found_jar:
            ver_match = re.search(r'(\d+[\.\d]+\d)', found_jar)
            raw(f'  {lib_name}:')
            raw(f'    present: true')
            raw(f'    jar: "{found_jar}"')
            raw(f'    version: "{ver_match.group(1) if ver_match else "unknown"}"')
        else:
            raw(f'  {lib_name}: false')
else:
    raw('  # lib/ directory not found — JAR scan skipped')
    warnings.append('lib/ directory not found — special library detection skipped')


# ─────────────────────────────────────────────────────────────────────────────
# 7. Warnings and metadata
# ─────────────────────────────────────────────────────────────────────────────

if warnings:
    lines.append('')
    lines.append('scan_warnings:')
    for w in warnings:
        lines.append(f'  - "{w}"')

lines.append('')
lines.append('scan_meta:')
lines.append(f'  timestamp: "{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}"')
lines.append(f'  project_root: "{os.getcwd()}"')
lines.append(f'  scanner_version: "1.0.0"')


# ─────────────────────────────────────────────────────────────────────────────
# Write output
# ─────────────────────────────────────────────────────────────────────────────

header = [
    '# EAR Project Scan Results',
    f'# Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
    '# This file is temporary — it will be deleted after app-manifest.yaml is generated.',
    '',
]

output = '\n'.join(header + lines) + '\n'

output_path = 'scan-output.yaml'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(output)

print(f'✓ Scan complete → {output_path}')
if warnings:
    print(f'\n⚠ Warnings ({len(warnings)}):')
    for w in warnings:
        print(f'  - {w}')
print()
print(output)
