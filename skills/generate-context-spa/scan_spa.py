#!/usr/bin/env python3
"""
scan_spa.py
-----------
Scans a Spring Boot + React SPA project and outputs scan-output.yaml.
Handles both monorepo (frontend/ inside Java project) and detects
Layout B (separate repos) gracefully.

Run from the project root:
    python3 .github/skills/generate-context-spa/scan_spa.py

Uses only the Python standard library — no pip installs required.
"""

import os
import re
import json
import glob
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


def find_dir(*patterns):
    for pattern in patterns:
        matches = [p for p in glob.glob(pattern, recursive=True) if os.path.isdir(p)]
        if matches:
            return matches[0]
    return None


def read_file(path):
    if not path or not os.path.exists(path):
        return ''
    try:
        return open(path, encoding='utf-8', errors='replace').read()
    except Exception:
        return ''


def read_json(path):
    try:
        return json.loads(read_file(path))
    except Exception:
        return {}


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
    dotted = '.'.join(keys)
    m = re.search(rf'^{re.escape(dotted)}\s*[=:]\s*(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"\'')
    last_key = keys[-1]
    m = re.search(rf'^\s+{re.escape(last_key)}\s*:\s*(.+)$', content, re.MULTILINE)
    if m:
        val = m.group(1).strip().strip('"\'')
        if val and not val.startswith('#'):
            return val
    return None


def dep_version(deps, *keys):
    """Return cleaned version string for any matching key."""
    for key in keys:
        v = deps.get(key, '')
        if v:
            return re.sub(r'^[\^~>=<]+', '', v).strip()
    return None


def detect_db_type(url):
    if not url:
        return 'unknown'
    url = url.lower()
    for db, kw in [('postgres', ['postgresql', 'postgres']),
                   ('oracle', ['oracle']),
                   ('mysql', ['mysql']),
                   ('sqlserver', ['sqlserver', 'mssql']),
                   ('h2', ['h2'])]:
        if any(k in url for k in kw):
            return db
    return 'unknown'


def detect_db_host(url):
    if not url:
        return 'unknown'
    url_lower = url.lower()
    if 'rds.amazonaws.com' in url_lower:
        return 'aws-rds'
    if 'database.azure.com' in url_lower:
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
# 0. Detect layout
# ─────────────────────────────────────────────────────────────────────────────

frontend_dir = find_dir('frontend', 'client', 'ui', 'web-app')
pom_path     = find_file('pom.xml')
gradle_path  = find_file('build.gradle', 'build.gradle.kts')

# Detect frontend-maven-plugin in pom.xml
has_frontend_plugin = False
if pom_path:
    pom_content = read_file(pom_path)
    has_frontend_plugin = 'frontend-maven-plugin' in pom_content

layout = 'monorepo' if (frontend_dir or has_frontend_plugin) else 'separate-repos'

section('project_layout')
field('layout', layout)
field('frontend_directory', frontend_dir or 'not detected')
field('backend_directory', 'project root')
field('frontend_maven_plugin', has_frontend_plugin)

if layout == 'separate-repos':
    warnings.append(
        'No frontend/ directory detected. This may be a separate-repos layout. '
        'Frontend sections will be incomplete. Run the scanner from the frontend '
        'project root separately if needed.'
    )

# Resolve paths for frontend config files
fe_root = frontend_dir or '.'


# ─────────────────────────────────────────────────────────────────────────────
# 1. Backend — build info (pom.xml or build.gradle)
# ─────────────────────────────────────────────────────────────────────────────

section('backend_build', 'Spring Boot backend')

pom = parse_xml(pom_path)

if pom_path:
    sb_version  = find_text(pom, 'parent', 'version')
    props       = pom.find('properties') if pom is not None else None
    java_ver    = None
    if props is not None:
        for tag in ('java.version', 'maven.compiler.source', 'maven.compiler.release'):
            elem = props.find(tag)
            if elem is not None and elem.text:
                java_ver = elem.text.strip()
                break

    field('build_tool', 'maven')
    field('spring_boot_version', sb_version or 'check pom.xml parent')
    field('java_version', java_ver or 'check pom.xml properties')
    field('packaging', find_text(pom, 'packaging') or 'jar')

elif gradle_path:
    content     = read_file(gradle_path)
    sb_match    = re.search(r"id['\"]org\.springframework\.boot['\"].*?version['\"]([^'\"]+)['\"]", content)
    java_match  = re.search(r'(?:sourceCompatibility|javaVersion)\s*[=:]\s*[\'"]?([^\s\'"]+)', content)
    field('build_tool', 'gradle')
    field('spring_boot_version', sb_match.group(1) if sb_match else 'check build.gradle')
    field('java_version', java_match.group(1) if java_match else 'check build.gradle')
    field('packaging', 'jar')

else:
    field('build_tool', 'not_found')
    warnings.append('pom.xml and build.gradle not found')


# ─────────────────────────────────────────────────────────────────────────────
# 2. Backend — application config
# ─────────────────────────────────────────────────────────────────────────────

app_config_path = find_file(
    'src/main/resources/application.yml',
    'src/main/resources/application.yaml',
    'src/main/resources/application.properties',
)
app_config = read_file(app_config_path)

section('backend_config', 'Spring Boot application config')
field('app_name',    yml_value(app_config, 'spring', 'application', 'name') or 'unknown')
field('server_port', yml_value(app_config, 'server', 'port') or '8080')

# CORS config
cors_origins = re.findall(r'(?:allowed-origins|allowedOrigins)\s*[=:]\s*(.+)', app_config)
if cors_origins:
    raw('  cors_origins:')
    for origin in cors_origins[:5]:
        raw(f'    - "{origin.strip()}"')
else:
    raw('  cors_origins: []  # not detected — check security config')

# Auth hints
has_security = False
if pom_path:
    has_security = 'spring-boot-starter-security' in read_file(pom_path)
jwt_hint = bool(re.search(r'jwt|oauth|token', app_config, re.I))
field('spring_security', has_security)
field('jwt_or_oauth_detected', jwt_hint)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Backend — database
# ─────────────────────────────────────────────────────────────────────────────

section('backend_database')

ds_url     = yml_value(app_config, 'spring', 'datasource', 'url')
db_type    = detect_db_type(ds_url)
db_host    = detect_db_host(ds_url)
dialect    = yml_value(app_config, 'spring', 'jpa', 'properties', 'hibernate', 'dialect') or \
             yml_value(app_config, 'spring', 'jpa', 'database-platform')

# Dependency overrides for db type
if db_type == 'unknown' and pom_path:
    pom_content = read_file(pom_path)
    if 'ojdbc' in pom_content:
        db_type = 'oracle'
    elif 'postgresql' in pom_content:
        db_type = 'postgres'
    elif 'mysql-connector' in pom_content:
        db_type = 'mysql'

migration_tool = 'none'
flyway_count   = 0
if pom_path:
    pc = read_file(pom_path)
    if 'flyway-core' in pc:
        migration_tool = 'flyway'
        flyway_dir = find_file('src/main/resources/db/migration')
        if flyway_dir and os.path.isdir(flyway_dir):
            flyway_count = len(glob.glob(os.path.join(flyway_dir, '*.sql')))
    elif 'liquibase-core' in pc:
        migration_tool = 'liquibase'

orm = 'none'
if pom_path:
    pc = read_file(pom_path)
    if 'spring-boot-starter-data-jpa' in pc:
        orm = 'spring-data-jpa'
    elif 'spring-boot-starter-jdbc' in pc:
        orm = 'jdbc-template'

field('type',            db_type)
field('host',            db_host)
field('orm',             orm)
field('dialect',         dialect or 'not specified')
field('migration_tool',  migration_tool)
if flyway_count:
    field('flyway_migration_count', str(flyway_count))
field('heavy_stored_procs', False, comment='confirm with engineer')


# ─────────────────────────────────────────────────────────────────────────────
# 4. Backend — API and OpenAPI
# ─────────────────────────────────────────────────────────────────────────────

section('backend_api')

openapi_path = find_file(
    'src/main/resources/openapi.yaml',
    'src/main/resources/openapi.yml',
    'src/main/resources/static/openapi.yaml',
    'api/openapi.yaml',
)

has_web = pom_path and ('spring-boot-starter-web' in read_file(pom_path))
has_openapi_docs = pom_path and ('springdoc-openapi' in read_file(pom_path) or
                                  'springfox' in read_file(pom_path))

field('type',                    'rest' if has_web else 'none')
field('openapi_spec_path',       openapi_path or 'not found')
field('openapi_docs_auto_gen',   has_openapi_docs)

# Parse endpoints from OpenAPI spec if present
if openapi_path:
    spec_content = read_file(openapi_path)
    endpoints = []
    in_paths = False
    current_path = None
    for line in spec_content.splitlines():
        if re.match(r'^paths\s*:', line):
            in_paths = True
            continue
        if in_paths:
            if re.match(r'^\S', line):
                in_paths = False
                continue
            pm = re.match(r'^  (/[^\s:]+)\s*:', line)
            if pm:
                current_path = pm.group(1)
            mm = re.match(r'^    (get|post|put|delete|patch)\s*:', line, re.I)
            if mm and current_path:
                endpoints.append(f'{mm.group(1).upper()} {current_path}')
    if endpoints:
        raw('  endpoints:')
        for ep in endpoints[:20]:
            raw(f'    - "{ep}"')
        if len(endpoints) > 20:
            raw(f'    # ... and {len(endpoints) - 20} more in {openapi_path}')
    else:
        raw('  endpoints: []  # populate from question 12 or read OpenAPI spec')
else:
    raw('  endpoints: []  # populate from question 12 or read OpenAPI spec')


# ─────────────────────────────────────────────────────────────────────────────
# 5. Frontend — package.json
# ─────────────────────────────────────────────────────────────────────────────

section('frontend_stack', 'React frontend')

pkg_path = find_file(
    os.path.join(fe_root, 'package.json'),
    'package.json',
)
pkg = read_json(pkg_path)
all_deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}

if pkg_path:
    # Core
    react_ver = dep_version(all_deps, 'react')
    field('framework',       'react')
    field('react_version',   react_ver or 'check package.json')

    # Language
    is_ts = 'typescript' in all_deps or os.path.exists(
        os.path.join(fe_root, 'tsconfig.json')) or os.path.exists('tsconfig.json')
    field('language',        'typescript' if is_ts else 'javascript')

    # Build tool
    build_tool = 'unknown'
    if 'vite' in all_deps:
        build_tool = 'vite'
    elif 'react-scripts' in all_deps:
        build_tool = 'cra'
    elif '@craco/craco' in all_deps:
        build_tool = 'craco'
    elif 'webpack' in all_deps:
        build_tool = 'webpack'
    field('build_tool',      build_tool)

    # Package manager
    pkg_manager = 'npm'
    if os.path.exists(os.path.join(fe_root, 'yarn.lock')) or os.path.exists('yarn.lock'):
        pkg_manager = 'yarn'
    elif os.path.exists(os.path.join(fe_root, 'pnpm-lock.yaml')) or os.path.exists('pnpm-lock.yaml'):
        pkg_manager = 'pnpm'
    field('package_manager', pkg_manager)

    # Node version
    node_ver = None
    for nv_file in ['.nvmrc', '.node-version']:
        nv_path = os.path.join(fe_root, nv_file) if fe_root != '.' else nv_file
        if os.path.exists(nv_path):
            node_ver = read_file(nv_path).strip().lstrip('v')
            break
    if not node_ver:
        node_ver = (pkg.get('engines') or {}).get('node', None)
        if node_ver:
            node_ver = re.sub(r'[>=<^~]', '', node_ver).strip()
    field('node_version', node_ver or 'check .nvmrc or engines in package.json')

    # State management
    state_mgmt = 'none'
    if '@reduxjs/toolkit' in all_deps or 'redux' in all_deps:
        state_mgmt = 'redux'
    elif 'zustand' in all_deps:
        state_mgmt = 'zustand'
    elif 'mobx' in all_deps:
        state_mgmt = 'mobx'
    elif 'jotai' in all_deps:
        state_mgmt = 'jotai'
    elif 'recoil' in all_deps:
        state_mgmt = 'recoil'
    field('state_management', state_mgmt)

    # Routing
    routing = 'none'
    if 'react-router-dom' in all_deps or 'react-router' in all_deps:
        routing = 'react-router'
    elif '@tanstack/react-router' in all_deps:
        routing = 'tanstack-router'
    elif 'wouter' in all_deps:
        routing = 'wouter'
    field('routing', routing)

    # UI component library
    ui_lib = 'none'
    ui_candidates = [
        ('@mui/material', 'mui-v5'),
        ('@material-ui/core', 'mui-v4'),
        ('antd', 'ant-design'),
        ('@chakra-ui/react', 'chakra-ui'),
        ('primereact', 'primereact'),
        ('@mantine/core', 'mantine'),
        ('semantic-ui-react', 'semantic-ui'),
        ('@nextui-org/react', 'nextui'),
    ]
    for pkg_name, label in ui_candidates:
        if pkg_name in all_deps:
            ui_lib = label
            break
    # Tailwind detection (utility-first, not a component lib)
    has_tailwind = 'tailwindcss' in all_deps
    has_shadcn   = any('radix-ui' in k for k in all_deps.keys())
    field('ui_library',      ui_lib)
    field('tailwind',        has_tailwind)
    field('shadcn_radix',    has_shadcn)

    # HTTP client
    http_client = 'fetch'
    if 'axios' in all_deps:
        http_client = 'axios'
    has_react_query = '@tanstack/react-query' in all_deps or 'react-query' in all_deps
    has_swr         = 'swr' in all_deps
    field('http_client',     http_client)
    field('react_query',     has_react_query)
    field('swr',             has_swr)

    # Form library
    form_lib = 'none'
    if 'react-hook-form' in all_deps:
        form_lib = 'react-hook-form'
    elif 'formik' in all_deps:
        form_lib = 'formik'
    field('form_library', form_lib)

    # Internationalisation
    has_i18n = 'i18next' in all_deps or 'react-intl' in all_deps or 'react-i18next' in all_deps
    field('i18n', has_i18n)

    # Testing
    raw('  testing:')
    field('unit',        'vitest' if 'vitest' in all_deps else ('jest' if 'jest' in all_deps else 'none'), indent=2)
    field('component',   '@testing-library/react' in all_deps, indent=2)
    field('e2e',         'playwright' if '@playwright/test' in all_deps else ('cypress' if 'cypress' in all_deps else 'none'), indent=2)

else:
    raw('  # package.json not found — frontend may be in a separate repo')
    warnings.append('package.json not found — frontend stack not scanned')


# ─────────────────────────────────────────────────────────────────────────────
# 6. Frontend — build config (Vite / Webpack / CRACO)
# ─────────────────────────────────────────────────────────────────────────────

section('frontend_build_config')

vite_config = find_file(
    os.path.join(fe_root, 'vite.config.ts'),
    os.path.join(fe_root, 'vite.config.js'),
    'vite.config.ts', 'vite.config.js',
)
webpack_config = find_file(
    os.path.join(fe_root, 'webpack.config.js'),
    'webpack.config.js',
)
craco_config = find_file(
    os.path.join(fe_root, 'craco.config.js'),
    'craco.config.js',
)

# Detect API proxy target — tells us the backend base URL
api_proxy_target = None
for cfg_path in filter(None, [vite_config, webpack_config, craco_config]):
    cfg_content = read_file(cfg_path)
    # Vite proxy: target: 'http://localhost:8080'
    m = re.search(r"target\s*:\s*['\"]([^'\"]+)['\"]", cfg_content)
    if m:
        api_proxy_target = m.group(1)
        break
    # Webpack devServer.proxy
    m = re.search(r"proxy\s*:.*?['\"](['\"]?http[s]?://[^'\"]+)['\"]", cfg_content, re.S)
    if m:
        api_proxy_target = m.group(1).strip('"\'')
        break

field('config_file', vite_config or webpack_config or craco_config or 'not found')
field('api_proxy_target', api_proxy_target or 'not detected — check .env or build config')

# Detect env files
env_files = glob.glob(os.path.join(fe_root, '.env*')) + glob.glob('.env*')
env_file_names = [os.path.basename(f) for f in env_files if '.env' in os.path.basename(f)]
if env_file_names:
    raw('  env_files:')
    for ef in sorted(set(env_file_names))[:6]:
        raw(f'    - "{ef}"')
else:
    raw('  env_files: []')


# ─────────────────────────────────────────────────────────────────────────────
# 7. Deployment
# ─────────────────────────────────────────────────────────────────────────────

section('deployment')

dockerfile  = find_file('Dockerfile', 'docker/Dockerfile')
helm_chart  = find_file('helm/Chart.yaml', 'charts/Chart.yaml')
helm_values = find_file('helm/values.yaml', 'charts/values.yaml')
nginx_conf  = find_file('nginx.conf', 'docker/nginx.conf', 'frontend/nginx.conf')

field('containerized',       bool(dockerfile))
field('helm_chart',          bool(helm_chart))
field('nginx_config_found',  bool(nginx_conf))

# Serving mode
if has_frontend_plugin or (pom_path and 'static' in read_file(pom_path)):
    serving_mode = 'spring-boot-static'
elif nginx_conf:
    serving_mode = 'nginx-container'
else:
    serving_mode = 'unknown — check question 4'
field('frontend_serving', serving_mode)

# Platform
platform = 'unknown'
if helm_values:
    hv = read_file(helm_values).lower()
    if 'aks' in hv or 'azure' in hv:
        platform = 'aks'
    elif 'eks' in hv or 'aws' in hv:
        platform = 'eks'
if platform == 'unknown':
    ds_url_str = yml_value(app_config, 'spring', 'datasource', 'url') or ''
    if 'rds.amazonaws' in ds_url_str:
        platform = 'eks (inferred from RDS datasource)'
    elif 'database.azure' in ds_url_str:
        platform = 'aks (inferred from Azure datasource)'
field('platform', platform)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Design system hints
# ─────────────────────────────────────────────────────────────────────────────

section('design_system_hints')

# Storybook
has_storybook = '@storybook/react' in all_deps or bool(find_dir('.storybook'))
field('storybook', has_storybook)

# Design tokens (Style Dictionary, Theo, etc.)
has_tokens = 'style-dictionary' in all_deps or bool(find_file('**/tokens.json', '**/design-tokens.json'))
field('design_tokens_detected', has_tokens)

# CSS approach
has_css_modules = bool(find_file('**/*.module.css', '**/*.module.scss'))
has_styled_components = 'styled-components' in all_deps
has_emotion = '@emotion/react' in all_deps
css_approach = 'css-modules' if has_css_modules else \
               'styled-components' if has_styled_components else \
               'emotion' if has_emotion else \
               'tailwind' if has_tailwind else 'plain-css'
field('css_approach', css_approach)


# ─────────────────────────────────────────────────────────────────────────────
# 9. Warnings and metadata
# ─────────────────────────────────────────────────────────────────────────────

if not pom_path and not gradle_path:
    warnings.append('No Java build file found — is this the project root?')
if not app_config_path:
    warnings.append('application.yml not found — backend config not scanned')
if not pkg_path:
    warnings.append('package.json not found — frontend stack not scanned')

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
    '# Spring Boot + React SPA Scan Results',
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
