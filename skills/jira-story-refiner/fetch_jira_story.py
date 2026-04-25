#!/usr/bin/env python3
"""
fetch_jira_story.py
-------------------
Fetches a Jira issue by URL and writes formatted content to jira-story-raw.txt.

Usage:
    python3 .github/skills/jira-story-refiner/fetch_jira_story.py <jira-url>

Authentication (set one of the following before running):

  Jira Server / Data Center (Personal Access Token):
    export JIRA_TOKEN=<your-pat>

  Jira Cloud (API Token):
    export JIRA_EMAIL=<your-email>
    export JIRA_TOKEN=<your-api-token>

Output:
    Writes jira-story-raw.txt to the project root (current working directory).

Uses only the Python standard library — no pip installs required.
"""

import sys
import os
import re
import json
import base64
import urllib.request
import urllib.error
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_issue_key(url):
    """Extract Jira issue key from a browse URL."""
    # Matches patterns like /browse/PROJ-1234 or /issues/PROJ-1234
    m = re.search(r'/(?:browse|issues?)/([A-Z][A-Z0-9_]+-\d+)', url)
    if m:
        return m.group(1)
    # Also try raw issue key at end of URL
    m = re.search(r'([A-Z][A-Z0-9_]+-\d+)(?:\?|$)', url)
    if m:
        return m.group(1)
    return None


def extract_base_url(url):
    """Extract base Jira URL (scheme + host) from a browse URL."""
    m = re.match(r'(https?://[^/]+)', url)
    return m.group(1) if m else None


def build_auth_header():
    """Build Authorization header from environment variables."""
    token = os.environ.get('JIRA_TOKEN', '').strip()
    email = os.environ.get('JIRA_EMAIL', '').strip()

    if not token:
        return None, "JIRA_TOKEN environment variable is not set."

    if email:
        # Jira Cloud: Basic auth with email:token
        creds = base64.b64encode(f'{email}:{token}'.encode()).decode()
        return f'Basic {creds}', None
    else:
        # Jira Server / Data Center: Bearer PAT
        return f'Bearer {token}', None


def flatten_adf(node):
    """
    Recursively flatten Atlassian Document Format (ADF) to plain text.
    ADF is used by Jira Cloud for rich text fields.
    """
    if not node:
        return ''

    node_type = node.get('type', '')
    text = ''

    if node_type == 'text':
        text = node.get('text', '')

    elif node_type in ('paragraph', 'heading'):
        children = ''.join(flatten_adf(c) for c in node.get('content', []))
        text = children + '\n'

    elif node_type == 'bulletList':
        items = []
        for item in node.get('content', []):
            item_text = ''.join(flatten_adf(c) for c in item.get('content', []))
            items.append(f'- {item_text.strip()}')
        text = '\n'.join(items) + '\n'

    elif node_type == 'orderedList':
        items = []
        for i, item in enumerate(node.get('content', []), 1):
            item_text = ''.join(flatten_adf(c) for c in item.get('content', []))
            items.append(f'{i}. {item_text.strip()}')
        text = '\n'.join(items) + '\n'

    elif node_type == 'codeBlock':
        code = ''.join(c.get('text', '') for c in node.get('content', []))
        text = f'\n```\n{code}\n```\n'

    elif node_type == 'blockquote':
        inner = ''.join(flatten_adf(c) for c in node.get('content', []))
        text = '\n'.join(f'> {line}' for line in inner.splitlines()) + '\n'

    elif node_type == 'hardBreak':
        text = '\n'

    elif node_type == 'rule':
        text = '\n---\n'

    elif node_type in ('doc', 'listItem', 'tableRow', 'tableCell', 'tableHeader', 'table'):
        text = ''.join(flatten_adf(c) for c in node.get('content', []))

    else:
        # Fallback: recurse into content
        text = ''.join(flatten_adf(c) for c in node.get('content', []))

    return text


def parse_description(fields):
    """
    Parse the description field, handling both:
    - ADF (Jira Cloud): description is a dict with type='doc'
    - Wiki markup (Jira Server): description is a plain string
    """
    desc = fields.get('description')
    if not desc:
        return '(No description provided)'

    if isinstance(desc, dict) and desc.get('type') == 'doc':
        # ADF format (Jira Cloud)
        return flatten_adf(desc).strip()
    elif isinstance(desc, str):
        # Plain text or wiki markup (Jira Server)
        # Convert common wiki markup to readable text
        text = desc
        text = re.sub(r'\*([^*]+)\*', r'\1', text)         # *bold*
        text = re.sub(r'_([^_]+)_', r'\1', text)            # _italic_
        text = re.sub(r'\{\{([^}]+)\}\}', r'`\1`', text)   # {{code}}
        text = re.sub(r'h[1-6]\.\s', '', text)              # h1. headings
        text = re.sub(r'\[([^\|]+)\|[^\]]+\]', r'\1', text) # [text|url]
        return text.strip()

    return str(desc).strip()


def parse_acceptance_criteria(fields):
    """
    Try to find acceptance criteria in common Jira custom field names.
    Returns text or None.
    """
    # Common custom field names for acceptance criteria
    ac_candidates = [
        'customfield_10016',  # common in many Jira configs
        'customfield_10020',
        'customfield_10028',
        'customfield_10034',
        'acceptance_criteria',
        'acceptanceCriteria',
    ]

    for key in ac_candidates:
        val = fields.get(key)
        if val:
            if isinstance(val, dict) and val.get('type') == 'doc':
                return flatten_adf(val).strip()
            elif isinstance(val, str) and len(val) > 5:
                return val.strip()

    return None


def fetch_issue(base_url, issue_key, auth_header):
    """Fetch issue JSON from Jira REST API v2."""
    api_url = f'{base_url}/rest/api/2/issue/{issue_key}'

    req = urllib.request.Request(api_url)
    req.add_header('Authorization', auth_header)
    req.add_header('Accept', 'application/json')
    req.add_header('Content-Type', 'application/json')

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        raise RuntimeError(
            f'Jira API returned HTTP {e.code}.\n'
            f'URL: {api_url}\n'
            f'Response: {body[:500]}'
        )
    except urllib.error.URLError as e:
        raise RuntimeError(
            f'Cannot reach Jira at {base_url}.\n'
            f'Error: {e.reason}\n'
            f'Check that you are on the corporate network and the URL is correct.'
        )


def format_output(issue_key, data):
    """Format the Jira issue data as structured plain text."""
    fields = data.get('fields', {})

    summary   = fields.get('summary', '(no summary)')
    status    = (fields.get('status') or {}).get('name', 'unknown')
    priority  = (fields.get('priority') or {}).get('name', 'unknown')
    issue_type = (fields.get('issuetype') or {}).get('name', 'unknown')
    assignee  = (fields.get('assignee') or {}).get('displayName', 'unassigned')
    reporter  = (fields.get('reporter') or {}).get('displayName', 'unknown')
    labels    = ', '.join(fields.get('labels', [])) or 'none'
    components = ', '.join(
        (c.get('name', '') for c in fields.get('components', []))
    ) or 'none'

    description = parse_description(fields)
    acceptance_criteria = parse_acceptance_criteria(fields)

    lines = [
        f'# Jira Story: {issue_key}',
        f'Fetched: {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        '',
        '## Metadata',
        f'- **Type:** {issue_type}',
        f'- **Status:** {status}',
        f'- **Priority:** {priority}',
        f'- **Assignee:** {assignee}',
        f'- **Reporter:** {reporter}',
        f'- **Labels:** {labels}',
        f'- **Components:** {components}',
        '',
        '## Summary',
        summary,
        '',
        '## Description',
        description,
    ]

    if acceptance_criteria:
        lines += [
            '',
            '## Acceptance Criteria',
            acceptance_criteria,
        ]
    else:
        lines += [
            '',
            '## Acceptance Criteria',
            '(Not found in standard custom fields — check the Jira ticket manually)',
        ]

    # Linked issues
    links = fields.get('issuelinks', [])
    if links:
        lines += ['', '## Linked Issues']
        for link in links:
            link_type = (link.get('type') or {}).get('name', 'relates to')
            inward = link.get('inwardIssue')
            outward = link.get('outwardIssue')
            if inward:
                key_ref = inward.get('key', '')
                summary_ref = (inward.get('fields') or {}).get('summary', '')
                lines.append(f'- {link_type} ← {key_ref}: {summary_ref}')
            if outward:
                key_ref = outward.get('key', '')
                summary_ref = (outward.get('fields') or {}).get('summary', '')
                lines.append(f'- {link_type} → {key_ref}: {summary_ref}')

    return '\n'.join(lines) + '\n'


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print('Usage: python3 fetch_jira_story.py <jira-url>', file=sys.stderr)
        sys.exit(1)

    jira_url = sys.argv[1].strip()

    # Extract issue key and base URL
    issue_key = extract_issue_key(jira_url)
    if not issue_key:
        print(f'ERROR: Could not extract issue key from URL: {jira_url}', file=sys.stderr)
        print('Expected format: https://jira.company.com/browse/PROJ-1234', file=sys.stderr)
        sys.exit(1)

    base_url = extract_base_url(jira_url)
    if not base_url:
        print(f'ERROR: Could not extract base URL from: {jira_url}', file=sys.stderr)
        sys.exit(1)

    # Build auth header
    auth_header, err = build_auth_header()
    if err:
        print(f'ERROR: {err}', file=sys.stderr)
        print('Set the JIRA_TOKEN environment variable and retry.', file=sys.stderr)
        sys.exit(1)

    print(f'Fetching {issue_key} from {base_url} ...', file=sys.stderr)

    # Fetch issue
    try:
        data = fetch_issue(base_url, issue_key, auth_header)
    except RuntimeError as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)

    # Format and write output
    output = format_output(issue_key, data)
    output_path = 'jira-story-raw.txt'

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output)

    print(f'✓ Story written to {output_path}', file=sys.stderr)
    print(output)


if __name__ == '__main__':
    main()
