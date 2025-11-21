# RHDH Support Agent

## Overview

The RHDH Support Agent is a specialized AI agent designed to help Red Hat support teams manage RHDHSUPP issues that require Engineering assistance. It acts as a focal point between Customer Support and Engineering, tracking customer cases, JIRA issues, and ensuring proper prioritization based on severity and SLA requirements.

## Features

- **Multi-source integration**: JIRA (RHDHSUPP, RHDHPLAN, RHDHBUGS), Red Hat Customer Portal (RHCP), Google Drive, and Red Hat documentation
- **Read-only operations**: Safe querying without risk of modifying tickets or customer cases
- **Severity-to-priority mapping**: Automatic mapping of case severity to JIRA priority with escalation handling
- **Version support queries**: Fetch RHDH lifecycle information from Red Hat documentation
- **Customer case tracking**: Link JIRA issues to RHCP cases for full context
- **Extended system prompt**: Optional Google Doc integration for additional instructions

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ RHDHSupport (Wrapper)                               │
├─────────────────────────────────────────────────────┤
│ • Configuration management                          │
│ • Toolkit orchestration (5 toolkits)                │
│ • System prompt composition                         │
│ • Agent caching (per user_id)                       │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │ Agno Agent     │
         │ (per user)     │
         └────────────────┘
                  │
        ┌─────────┴──────────┐
        ▼                    ▼
   Configured          Not Configured
   ┌──────────┐       ┌──────────┐
   │ JIRA     │       │ RHCP     │
   │ GDrive   │       │          │
   │ Web      │       └──────────┘
   └──────────┘
```

## System Prompt Composition

The RHDH Support Agent builds the agent's system prompt in the following order:

1. **Base Instructions** (comprehensive, built-in)
   - Agent role and responsibilities
   - Available tools and integrations
   - Severity-to-priority mapping rules
   - JIRA field mappings (cf[12313441])
   - Output and behavioral guidelines

2. **Extended Instructions** (from Google Docs, optional)
   - Fetched from a Google Doc specified by `SUPPORT_AGENT_SYSTEM_PROMPT_GDRIVE_URL`
   - Cached per user until agent invalidation
   - See "Extended System Prompt" section below

3. **Toolkit-Specific Instructions** (dynamic, based on configured toolkits)
   - JIRA integration instructions (always available)
   - Google Drive usage instructions (when configured)
   - RHCP integration instructions (when configured)
   - Web scraping instructions (always available)

## Toolkits

### 1. JIRA Integration (Always Available)

**Purpose**: Query RHDHSUPP, RHDHPLAN, and RHDHBUGS issues

**Configuration**:
```bash
JIRA_EMAIL=your.email@redhat.com
JIRA_API_TOKEN=your_jira_token
```

**Key Fields**:
- `cf[12313441]`: Case number field (JQL syntax)
- `customfield_12313441`: Case number field (response)
- Assignee, Team, Priority, Status

**Example Queries**:
```jql
project = RHDHSUPP AND status != Closed ORDER BY priority DESC
project = RHDHSUPP AND cf[12313441] = 04312027
```

### 2. Red Hat Customer Portal (RHCP) - Optional

**Purpose**: Fetch customer case information (severity, escalation, entitlements)

**Configuration**:
User provides RHCP offline token in chat:
```
My RHCP offline token is <token>
```

**Available Tools**:
- `get_case(case_number)`: Get detailed case information
- `search_cases(query, limit)`: Search for cases

**Data Retrieved**:
- Severity (1-4)
- Escalation status (is_escalated)
- Entitlement level
- SLA information
- Case status

### 3. Google Drive - Required

**Purpose**: Access RHDH support process documentation

**Configuration**:
```bash
GDRIVE_CLIENT_ID=your_client_id
GDRIVE_CLIENT_SECRET=your_client_secret
```

**Key Documents**:
- RHDHSUPP CEE Process
- RHDHSUPP Engineering Process
- RHDHSUPP Simplified Workflow
- RHDHSUPP Playbook

### 4. Web Scraping (Always Available)

**Purpose**: Fetch Red Hat documentation for version support and plugin information

**Allowed Domains**: `*.redhat.com` only

**Key URLs**:
- RHDH Lifecycle: https://access.redhat.com/support/policy/updates/developerhub
- Plugin support levels: https://docs.redhat.com/en/documentation/red_hat_developer_hub/1.8/html-single/dynamic_plugins_reference/
- Red Hat severity definitions: https://access.redhat.com/support/policy/severity
- Red Hat SLA policy: https://access.redhat.com/support/offerings/production/sla

**Security**: Domain validation enforced - only *.redhat.com allowed

## Severity to Priority Mapping

The agent applies the following mapping when analyzing JIRA issues:

| Case Severity | JIRA Priority | Notes |
|--------------|---------------|-------|
| 1 (Urgent)   | Critical      | High severity, requires immediate attention |
| 2 (High)     | Major         | Significant impact |
| 3 (Normal)   | Normal        | Standard priority |
| 4 (Low)      | Minor         | Low impact |
| **Escalated** | **Blocker**  | **Overrides severity mapping** |

**Special Rule**: If `is_escalated=true` in RHCP case data, JIRA priority should be **Blocker** regardless of case severity.

**Reference**: [RHDHSUPP CEE Process - Severity Mapping](https://docs.google.com/document/d/153AHMAAV8aPQdtd80nrPLAROHHIvFnXqjYx0wa1ywxw/edit?tab=t.0#heading=h.j05we53vkmku)

## Extended System Prompt

### Overview

The RHDH Support Agent can fetch additional system prompt instructions from a Google Doc. This allows you to:

- Customize agent behavior without code changes
- Update support process instructions in real-time
- Share prompts across support teams
- Version control prompts using Google Docs revision history

### Configuration

#### 1. Environment Variable

Set the `SUPPORT_AGENT_SYSTEM_PROMPT_GDRIVE_URL` environment variable in your `.env.secrets` file:

```bash
# Full URL format
SUPPORT_AGENT_SYSTEM_PROMPT_GDRIVE_URL=https://docs.google.com/document/d/YOUR_DOC_ID/edit

# Or just the document ID
SUPPORT_AGENT_SYSTEM_PROMPT_GDRIVE_URL=YOUR_DOC_ID
```

#### 2. Prerequisites

- **Google Drive must be configured**: Users must have authorized Google Drive access
- **Document access**: Users must have read access to the specified Google Doc
- **Document format**: Must be a Google Docs document (not Sheets or Slides)

### How It Works

#### Fetch and Cache Flow

```
1. User creates first message
   ↓
2. Agent creation triggered
   ↓
3. Check if SUPPORT_AGENT_SYSTEM_PROMPT_GDRIVE_URL is set
   ↓ (yes)
4. Check if user has Google Drive configured
   ↓ (yes)
5. Check cache for this user's extended prompt
   ↓ (miss)
6. Fetch document content via Google Drive API
   ↓
7. Convert to markdown (automatic)
   ↓
8. Cache content for this user
   ↓
9. Append to agent instructions
   ↓
10. Create agent with combined instructions
```

#### Cache Invalidation

The cached extended prompt is invalidated when:

1. **User authorizes a new toolkit** (e.g., RHCP, Google Drive)
   - Triggers agent invalidation which clears both agent and system prompt cache

2. **Agent is manually invalidated** (future enhancement)

After invalidation, the next agent creation will fetch a fresh copy from Google Docs.

### Document Format

The Google Doc content is automatically converted to **markdown** format. You can use:

- **Headings**: `# Header`, `## Subheader`
- **Lists**: Bullet points and numbered lists
- **Bold/Italic**: `**bold**`, `*italic*`
- **Code**: Inline `` `code` `` and code blocks
- **Links**: `[text](url)`

#### Example Google Doc Structure

```markdown
# RHDH Support Agent Extended Instructions

## Current Focus Areas
- RHDH 1.8 GA support (released 2024-XX-XX)
- Critical CVE tracking for versions 1.6, 1.7, 1.8
- Plugin support level verification

## Common JIRA Queries
### Unassigned High Priority Issues
project = RHDHSUPP AND assignee is EMPTY AND priority in (Blocker, Critical) ORDER BY created DESC

### Issues Awaiting Engineering Response
project = RHDHSUPP AND status = "Waiting on Red Hat" AND Team is NOT EMPTY

## Escalation Procedures
1. Identify escalated cases (is_escalated=true from RHCP)
2. Verify JIRA priority is set to Blocker
3. Ensure issue is assigned to appropriate RHDH Scrum Team
4. Monitor SLA compliance

## Key Contacts
- Support Manager: support-manager@redhat.com
- Engineering Lead: eng-lead@redhat.com
```

### Best Practices

1. **Keep it focused**: Extended prompts should complement, not duplicate, base instructions
2. **Use clear sections**: Organize with markdown headings for readability
3. **Include current context**: Version numbers, active releases, critical issues
4. **Update regularly**: Keep JIRA queries and procedures current
5. **Monitor length**: Very long prompts may impact token usage and cost

## Configuration Reference

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SUPPORT_AGENT_SYSTEM_PROMPT_GDRIVE_URL` | No | None | Google Doc URL or ID containing extended system prompt |
| `GDRIVE_CLIENT_ID` | Yes | None | Google OAuth client ID |
| `GDRIVE_CLIENT_SECRET` | Yes | None | Google OAuth client secret |
| `JIRA_EMAIL` | Yes | None | JIRA email for authentication |
| `JIRA_API_TOKEN` | Yes | None | JIRA API token |
| `GEMINI_API_KEY` | Yes | None | Gemini API key for the underlying model |

### Runtime Configuration

Users provide tokens at runtime:

- **RHCP Offline Token**: User provides in chat when prompted
- **Google Drive OAuth**: User completes OAuth flow when prompted

### Agent Parameters

When creating a RHDHSupport instance:

```python
support_agent = RHDHSupport(
    shared_db=db,
    user_id="user123",
    session_id="session456",
    temperature=0.7,      # Optional: Model temperature (0.0-2.0)
    max_tokens=4096,      # Optional: Maximum response tokens
)
```

## Usage Examples

### Version Support Query

**User**: "Is RHDH 1.5 still supported?"

**Agent Actions**:
1. Uses `fetch_url` to get RHDH Lifecycle page
2. Parses version support information
3. Returns clear answer with support dates

### Customer Case Analysis

**User**: "Check the status of RHDHSUPP-297 and its linked customer case"

**Agent Actions**:
1. Queries JIRA for RHDHSUPP-297
2. Extracts `customfield_12313441` (case number)
3. Uses `get_case(case_number)` to fetch RHCP data
4. Returns combined information: JIRA status + case severity + escalation status

### Priority Verification

**User**: "Show me issues with mismatched priorities"

**Agent Actions**:
1. Queries JIRA for issues with `cf[12313441]` (has linked case)
2. For each issue, fetches RHCP case data
3. Compares JIRA priority with expected priority (based on severity mapping)
4. Returns table of mismatches

## Read-Only Operations

**CRITICAL**: The RHDH Support Agent operates in **read-only mode** for all integrations:

- **JIRA**: Can query and read issues, **cannot** create, update, or comment
- **RHCP**: Can fetch case information, **cannot** create or modify cases
- **Google Drive**: Can read documents, **cannot** modify or create files
- **Web**: Can fetch public documentation, **cannot** modify any content

This ensures the agent is safe to use without risk of unintended modifications.

## Troubleshooting

### RHCP Tools Not Available

**Symptom**: Agent says it doesn't have RHCP tools after providing token

**Solution**: Check logs for:
- Token validation errors
- Agent cache invalidation
- Toolkit collection results

### JIRA Query Syntax Errors

**Symptom**: Agent uses wrong field syntax for case number

**Issue**: JQL uses `cf[12313441]`, not `customfield_12313441`

**Correct**:
```jql
project = RHDHSUPP AND cf[12313441] = 04312027
```

**Incorrect**:
```jql
project = RHDHSUPP AND customfield_12313441 = 04312027
```

### Web Scraping Blocked

**Symptom**: Agent cannot fetch Red Hat documentation

**Causes**:
- Domain restriction (only *.redhat.com allowed)
- Network connectivity issues
- URL format errors

**Check**: Ensure URL is from *.redhat.com domain

## Development

### Adding New Toolkits

1. Create toolkit config class extending `BaseToolkitConfig`
2. Add to `_initialize_toolkit_configs()` in `rhdh_support_configurator.py`
3. Implement required methods: `is_configured()`, `get_toolkit()`, `get_agent_instructions()`

### Modifying System Prompt

Key files:
- `src/agentllm/agents/rhdh_support_configurator.py`: Base instructions and toolkit setup
- `src/agentllm/agents/toolkit_configs/`: Toolkit-specific configurations

### Testing

Run tests with:

```bash
nox -s test

# Specific tests
uv run pytest tests/test_rhdh_support*.py -v
```

## Architecture Notes

### Dual-Prompt Architecture

Similar to Release Manager, the RHDH Support Agent uses a **dual-prompt architecture**:

**Embedded System Prompt** (in `rhdh_support_configurator.py`):
- **What it contains**: Core identity, responsibilities, tools, field mappings, severity mapping
- **Purpose**: "Who you are and what you can do"
- **Characteristics**: Stable, version-controlled, changes with code releases
- **Examples**:
  - Identity as RHDH Support Focal
  - Tool integrations (JIRA, RHCP, Web)
  - Severity-to-priority mapping rules
  - JQL field syntax (cf[12313441])

**External System Prompt** (fetched from Google Drive):
- **What it contains**: Current support context, active releases, common queries, procedures
- **Purpose**: "What you're currently working on and how to do it"
- **Characteristics**: Frequently updated, context-specific, operational details
- **Examples**:
  - Active RHDH versions and support dates
  - Common JIRA query templates
  - Escalation procedures
  - Key contacts and resources

**Design Benefits**:
- **Code changes** for capability updates (new tools, behavior changes)
- **Doc updates** for operational changes (new procedures, updated queries)
- Easy testing of prompt changes without code deployment
- Clear separation of concerns between stable identity and dynamic context

## Future Enhancements

- [ ] SLA tracking and alerts
- [ ] Automatic priority validation and correction suggestions
- [ ] Integration with Red Hat support ticket system
- [ ] Custom JIRA query templates per team
- [ ] Metrics and analytics on issue resolution times
- [ ] Automatic weekly summary reports
