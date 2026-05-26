# Coolify Deployment

Production runs from Git, not from the local development checkout.

## Source

- Repository: `https://github.com/hram/career-portal.git`
- Branch: `main`
- Build pack: Dockerfile
- Port: `8000`
- URL: `http://career-portal.192.168.1.72.sslip.io`

## Persistent Data

Prepared host path on `dev-server`:

```text
/srv/career-portal/data
```

Mount it inside the container to:

```text
/data/career-portal
```

This directory stores:

- `career_portal.db`
- `uploads/`
- `.claude/` if production Claude CLI auth is used

## Environment Variables

Use `.env.production.example` as the template in Coolify.

Required production paths:

```env
DATABASE_URL=sqlite:////data/career-portal/career_portal.db
CAREER_PORTAL_UPLOAD_DIR=/data/career-portal/uploads
HOME=/data/career-portal
CLAUDE_CLI_PATH=/usr/local/bin/claude
PORT=8000
```

## Initial Data Migration

Current runtime data was copied from the development machine to:

```text
/srv/career-portal/data
```

Original copy command:

```bash
ssh hram@192.168.1.72 'rm -rf /tmp/career-portal-data && mkdir -p /tmp/career-portal-data/uploads'
rsync -a /home/hram/projects/career-portal/career_portal.db hram@192.168.1.72:/tmp/career-portal-data/career_portal.db
rsync -a /home/hram/projects/career-portal/uploads/ hram@192.168.1.72:/tmp/career-portal-data/uploads/
ssh hram@192.168.1.72 'sudo mkdir -p /srv/career-portal/data && sudo rsync -a --delete /tmp/career-portal-data/ /srv/career-portal/data/'
```

Use the prepared host path as the Coolify persistent storage source.

## Current Status

- Coolify URL: `http://career-portal.192.168.1.72.sslip.io`
- Runtime data: `/srv/career-portal/data`
- Container data path: `/data/career-portal`

## Notes

- Do not commit `.env`, database files, uploaded resumes, generated previews, or API tokens.
- Do not commit Claude auth files from `/srv/career-portal/data/.claude`.
