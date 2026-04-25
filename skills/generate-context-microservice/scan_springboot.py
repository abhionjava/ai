#!/usr/bin/env python3
"""
scan_springboot.py
------------------
Scans a Spring Boot microservice project and outputs scan-output.yaml
to the project root.

Run from the project root:
    python3 .github/skills/generate-context-microservice/scan_springboot.py

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
    for pattern in patterns:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return matches[0]
    return None


def read_file(path):
    try:
        return open(path, encoding='utf-8', errors='replace').read()
    except Exception:
        return ''


def parse_xml(path):
    if not path or not os.path.exists(path):
        return None
    try:
        content = read_file(path)
        content = re.sub(r'\sxmlns(?::\w+)?="[^"]+"', '', content)
        content = re.sub(r'<(\w+:)', '<', content)
        content = re.sub(r'</(\w+:)', '</', content)
        return ET.fromstring(content)
    except Exception:
        return None


def find_text(root, *path):
    if root is None:
        return None
    node = root
    for tag in path:
        node = node.find(tag)
        if node is None:
            return None
    return node.text.strip() if node.text else None


def yml_value(content, *keys):
    """
    Extract a scalar value from application.yml using regex.
    Handles both flat (spring.datasource.url=...) and nested YAML.
    Tries dotted key first (properties format), then nested YAML key.
    """
    # Properties format: spring.datasource.url=jdbc:...
    dotted = '.'.join(keys)
    m = re.search(rf'^{re.escape(dotted)}\s*[=:]\s*(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"\'')

    # YAML nested format — match the last key indented under the others
    last_key = keys[-1]
    m = re.search(rf'^\s+{re.escape(last_key)}\s*:\s*(.+)$', content, re.MULTILINE)
    if m:
        val = m.group(1).strip().strip('"\'')
        if val and not val.startswith('#'):
            return val
    return None


def detect_db_type(url):
    if not url:
        return 'unknown'
    url = url.lower()
    if 'postgresql' in url or 'postgres' in url:
        return 'postgres'
    if 'oracle' in url:
        return 'oracle'
    if 'mysql' in url:
        return 'mysql'
    if 'sqlserver' in url or 'mssql' in url:
        return 'sqlserver'
    if 'h2' in url:
        return 'h2'
    return 'unknown'


def detect_db_host(url):
    if not url:
        return 'unknown'
    url_lower = url.lower()
    if 'rds.amazonaws.com' in url_lower or 'rds.amazon' in url_lower:
        return 'aws-rds'
    if 'database.azure.com' in url_lower or 'postgres.database' in url_lower:
        return 'azure-postgres'
    if 'localhost' in url_lower or '127.0.0.1' in url_lower:
        return 'local'
    return 'check application config'


# ─────────────────────────────────────────────────────────────────────────────
# Output builder
# ─────────────────────────────────────────────────────────────────────────────

lines = []
warnings = []


def section(name, comment=''):
    lines.append('')
    if comment:
        lines.append(f'# {comment}')
    lines.append(f'{name}:')


def field(key, value, indent=1, comment=''):
    pad = '  ' * indent
    suffix = f'  # {comment}' if comment else ''
    if isinstance(value, bool):
        lines.append(f'{pad}{key}: {str(value).lower()}{suffix}')
    elif value is None:
        lines.append(f'{pad}{key}: null{suffix}')
    else:
        safe = str(value).replace('"', '\\"')
        lines.append(f'{pad}{key}: "{safe}"{suffix}')


def raw(text):
    lines.append(text)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Build info (pom.xml or build.gradle)
# ─────────────────────────────────────────────────────────────────────────────

section('build')

pom_path = find_file('pom.xml')
gradle_path = find_file('build.gradle', 'build.gradle.kts')

if pom_path:
    pom = parse_xml(pom_path)
    field('build_tool', 'maven')

    # Spring Boot version from parent stanza
    sb_version = find_text(pom, 'parent', 'version')
    field('spring_boot_version', sb_version or 'check pom.xml parent')

    # Java version from properties
    props = pom.find('properties') if pom is not None else None
    java_ver = None
    if props is not None:
        for tag in ('java.version', 'maven.compiler.source', 'maven.compiler.release'):
            elem = props.find(tag)
            if elem is not None and elem.text:
                java_ver = elem.text.strip()
                break
    field('java_version', java_ver or 'check pom.xml properties')

    # Packaging
    pkg = find_text(pom, 'packaging')
    field('packaging', pkg or 'jar')

elif gradle_path:
    content = read_file(gradle_path)
    field('build_tool', 'gradle')

    sb_match = re.search(r"id['\"]org\.springframework\.boot['\"].*?version['\"]([^'\"]+)['\"]",
                         content)
    field('spring_boot_version', sb_match.group(1) if sb_match else 'check build.gradle')

    java_match = re.search(r'(?:sourceCompatibility|javaVersion)\s*[=:]\s*[\'"]?([^\s\'"]+)',
                           content)
    field('java_version', java_match.group(1) if java_match else 'check build.gradle')
    field('packaging', 'jar')

else:
    field('build_tool', 'not_found')
    warnings.append('pom.xml and build.gradle not found in project root')


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dependencies — detect key libraries from pom.xml
# ─────────────────────────────────────────────────────────────────────────────

detected_deps = set()

DEPENDENCY_MAP = {
    'spring-boot-starter-web':       'spring_web',
    'spring-boot-starter-webflux':   'spring_webflux',
    'spring-boot-starter-data-jpa':  'spring_data_jpa',
    'spring-boot-starter-jdbc':      'spring_jdbc',
    'spring-boot-starter-amqp':      'rabbitmq',
    'spring-kafka':                  'kafka',
    'spring-boot-starter-activemq':  'activemq',
    'ibm-mq-spring-boot-starter':    'ibm_mq',
    'hapi-base':                     'hapi_hl7',
    'hapi-hl7v2':                    'hapi_hl7',
    'fop':                           'apache_fop',
    'itextpdf':                      'itext',
    'itext':                         'itext',
    'drools-core':                   'drools',
    'drools-spring':                 'drools',
    'kie-spring':                    'drools',
    'springdoc-openapi':             'openapi_docs',
    'springfox-swagger':             'openapi_docs',
    'spring-boot-starter-security':  'spring_security',
    'spring-boot-starter-actuator':  'actuator',
    'flyway-core':                   'flyway',
    'liquibase-core':                'liquibase',
    'ojdbc':                         'oracle_jdbc',
    'postgresql':                    'postgres_jdbc',
    'mysql-connector':               'mysql_jdbc',
}

if pom_path and pom is not None:
    deps_root = pom.find('dependencies')
    if deps_root is not None:
        for dep in deps_root.findall('dependency'):
            artifact_id = find_text(dep, 'artifactId') or ''
            for key, label in DEPENDENCY_MAP.items():
                if key in artifact_id.lower():
                    detected_deps.add(label)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Application config (application.yml or application.properties)
# ─────────────────────────────────────────────────────────────────────────────

app_config_path = find_file(
    'src/main/resources/application.yml',
    'src/main/resources/application.yaml',
    'src/main/resources/application.properties',
)

app_config = read_file(app_config_path) if app_config_path else ''

app_name = yml_value(app_config, 'spring', 'application', 'name') or 'unknown'
server_port = yml_value(app_config, 'server', 'port') or '8080'

section('service_config')
field('app_name', app_name)
field('server_port', server_port)

# ─────────────────────────────────────────────────────────────────────────────
# 4. API detection
# ─────────────────────────────────────────────────────────────────────────────

section('api')

has_web = 'spring_web' in detected_deps or 'spring_webflux' in detected_deps
openapi_path = find_file(
    'src/main/resources/openapi.yaml',
    'src/main/resources/openapi.yml',
    'src/main/resources/static/openapi.yaml',
    'src/main/resources/api.yaml',
    'api/openapi.yaml',
)

if has_web:
    if 'spring_webflux' in detected_deps:
        field('type', 'rest-reactive')
    else:
        field('type', 'rest')
else:
    field('type', 'none', comment='no spring-boot-starter-web detected')

field('openapi_spec_path', openapi_path or 'not found')
field('openapi_docs_auto_generated', 'openapi_docs' in detected_deps)

# Parse OpenAPI spec if found
openapi_endpoints = []
if openapi_path:
    spec_content = read_file(openapi_path)
    # Extract paths from OpenAPI YAML — find lines like "  /path:" under "paths:"
    in_paths = False
    current_path = None
    for line in spec_content.splitlines():
        if re.match(r'^paths\s*:', line):
            in_paths = True
            continue
        if in_paths:
            if re.match(r'^\S', line) and not line.startswith(' '):
                in_paths = False
                continue
            path_match = re.match(r'^  (/[^\s:]+)\s*:', line)
            if path_match:
                current_path = path_match.group(1)
            method_match = re.match(r'^    (get|post|put|delete|patch)\s*:', line, re.I)
            if method_match and current_path:
                openapi_endpoints.append(f'{method_match.group(1).upper()} {current_path}')

if openapi_endpoints:
    raw('  endpoints:')
    for ep in openapi_endpoints[:20]:  # cap at 20 to avoid huge output
        raw(f'    - "{ep}"')
    if len(openapi_endpoints) > 20:
        raw(f'    # ... and {len(openapi_endpoints) - 20} more — see {openapi_path}')
else:
    raw('  endpoints: []  # populate from question 11 or read OpenAPI spec')


# ─────────────────────────────────────────────────────────────────────────────
# 5. Messaging
# ─────────────────────────────────────────────────────────────────────────────

section('messaging')

messaging_type = 'none'
if 'rabbitmq' in detected_deps:
    messaging_type = 'rabbitmq'
elif 'kafka' in detected_deps:
    messaging_type = 'kafka'
elif 'activemq' in detected_deps:
    messaging_type = 'activemq'
elif 'ibm_mq' in detected_deps:
    messaging_type = 'ibm_mq'

field('type', messaging_type)

# Extract RabbitMQ queue names from config
if messaging_type == 'rabbitmq':
    queues = re.findall(r'(?:queue[s]?|routing.key)\s*[=:]\s*([^\s#\n]+)',
                        app_config, re.I)
    if queues:
        raw('  detected_queues:')
        for q in set(queues[:10]):
            raw(f'    - "{q}"')

# Extract Kafka topics from config
if messaging_type == 'kafka':
    topics = re.findall(r'topic[s]?\s*[=:]\s*([^\s#\n]+)', app_config, re.I)
    if topics:
        raw('  detected_topics:')
        for t in set(topics[:10]):
            raw(f'    - "{t}"')

raw('  inbound: []   # populate from question 3 (askQuestions)')
raw('  outbound: []  # populate from question 4 (askQuestions)')


# ─────────────────────────────────────────────────────────────────────────────
# 6. Database
# ─────────────────────────────────────────────────────────────────────────────

section('database')

ds_url = yml_value(app_config, 'spring', 'datasource', 'url')
db_type = detect_db_type(ds_url)
db_host = detect_db_host(ds_url)
dialect = yml_value(app_config, 'spring', 'jpa', 'properties', 'hibernate', 'dialect') or \
          yml_value(app_config, 'spring', 'jpa', 'database-platform')

# Override db_type if oracle_jdbc or postgres_jdbc detected in deps
if db_type == 'unknown':
    if 'oracle_jdbc' in detected_deps:
        db_type = 'oracle'
    elif 'postgres_jdbc' in detected_deps:
        db_type = 'postgres'
    elif 'mysql_jdbc' in detected_deps:
        db_type = 'mysql'

orm = 'none'
if 'spring_data_jpa' in detected_deps:
    orm = 'spring-data-jpa'
elif 'spring_jdbc' in detected_deps:
    orm = 'jdbc-template'

migration_tool = 'none'
if 'flyway' in detected_deps:
    migration_tool = 'flyway'
elif 'liquibase' in detected_deps:
    migration_tool = 'liquibase'

# Count Flyway migrations if present
migration_count = 0
flyway_dir = find_file('src/main/resources/db/migration')
if flyway_dir and os.path.isdir(flyway_dir):
    migration_count = len(glob.glob(os.path.join(flyway_dir, '*.sql')))

field('type', db_type)
field('host', db_host)
field('datasource_url_detected', bool(ds_url))
field('orm', orm)
field('dialect', dialect or 'not specified')
field('migration_tool', migration_tool)
if migration_count:
    field('flyway_migration_count', str(migration_count))
field('heavy_stored_procs', False, comment='confirm with engineer')


# ─────────────────────────────────────────────────────────────────────────────
# 7. Deployment
# ─────────────────────────────────────────────────────────────────────────────

section('deployment')

dockerfile_path = find_file('Dockerfile', 'docker/Dockerfile')
helm_path = find_file('helm/Chart.yaml', 'charts/Chart.yaml')
k8s_path = find_file('k8s/*.yaml', 'kubernetes/*.yaml')

field('containerized', bool(dockerfile_path))
field('helm_chart', bool(helm_path))

# Detect platform from Helm values or k8s manifests
platform = 'unknown'
helm_values = find_file('helm/values.yaml', 'charts/values.yaml')
if helm_values:
    hv_content = read_file(helm_values)
    if 'aks' in hv_content.lower() or 'azure' in hv_content.lower():
        platform = 'aks'
    elif 'eks' in hv_content.lower() or 'aws' in hv_content.lower():
        platform = 'eks'

# Fall back to datasource URL for platform hint
if platform == 'unknown':
    if db_host == 'aws-rds':
        platform = 'eks (inferred from RDS datasource)'
    elif db_host == 'azure-postgres':
        platform = 'aks (inferred from Azure datasource)'

field('platform', platform)

# Namespace from Helm values
if helm_values:
    ns_match = re.search(r'namespace\s*:\s*(\S+)', read_file(helm_values))
    field('namespace', ns_match.group(1) if ns_match else 'check helm/values.yaml')
else:
    field('namespace', 'not detected')


# ─────────────────────────────────────────────────────────────────────────────
# 8. Special libraries
# ─────────────────────────────────────────────────────────────────────────────

section('special_libs')

SPECIAL_LIBS = {
    'hapi_hl7':   'hapi_hl7' in detected_deps,
    'apache_fop': 'apache_fop' in detected_deps,
    'itext':      'itext' in detected_deps,
    'drools':     'drools' in detected_deps,
}

for lib, present in SPECIAL_LIBS.items():
    raw(f'  {lib}: {str(present).lower()}')

# Drools — look for rule files in resources
if SPECIAL_LIBS['drools']:
    drl_files = glob.glob('src/main/resources/**/*.drl', recursive=True)
    xl_rules  = glob.glob('src/main/resources/**/*.xlsx', recursive=True)
    if drl_files:
        raw(f'  drools_drl_files: {len(drl_files)}')
    if xl_rules:
        raw(f'  drools_excel_rules: {len(xl_rules)}')


# ─────────────────────────────────────────────────────────────────────────────
# 9. Security
# ─────────────────────────────────────────────────────────────────────────────

section('security')
field('spring_security', 'spring_security' in detected_deps)
field('actuator_exposed', 'actuator' in detected_deps)


# ─────────────────────────────────────────────────────────────────────────────
# 10. Warnings and metadata
# ─────────────────────────────────────────────────────────────────────────────

if not pom_path and not gradle_path:
    warnings.append('No build file found — is this the project root?')
if not app_config_path:
    warnings.append('application.yml / application.properties not found')
if db_type == 'unknown':
    warnings.append('Database type could not be detected — check datasource config')
if platform == 'unknown':
    warnings.append('Deployment platform (AKS/EKS) could not be detected')

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
    '# Spring Boot Microservice Scan Results',
    f'# Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
    '# This file is temporary — deleted after app-manifest.yaml is generated.',
    '',
]

output = '\n'.join(header + lines) + '\n'

with open('scan-output.yaml', 'w', encoding='utf-8') as f:
    f.write(output)

print('✓ Scan complete → scan-output.yaml')
if warnings:
    print(f'\n⚠ Warnings ({len(warnings)}):')
    for w in warnings:
        print(f'  - {w}')
print()
print(output)
