# Run the security audit

Use Bash from the repository root. AWS CLI is not required.

1. Install dependencies. Skip the first two commands if uv is already installed.

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   export PATH="$HOME/.local/bin:$PATH"
   uv python install 3.13 3.12
   uv sync --locked
   ```

2. Set AWS access. **CloudShell:** use the current console session. **Local Bash:** replace the placeholders with your access keys:

   ```bash
   export AWS_ACCESS_KEY_ID='YOUR_ACCESS_KEY_ID'
   export AWS_SECRET_ACCESS_KEY='YOUR_SECRET_ACCESS_KEY'
   ```

   For temporary credentials, also set `AWS_SESSION_TOKEN`. Recommended read policies: `SecurityAudit` and `ViewOnlyAccess`.

   The script does not read `config_credentials.json` or load `.env`. `AWS_PROFILE` is optional.

3. Run the audit. Replace `dtcBattery` with the deployed `digital_twin_name` and set its AWS region:

   ```bash
   uv run python scripts/security_audit.py --twin dtcBattery --region eu-west-1
   ```

Reports are saved in `security-audit-output/`.

For all options: `uv run python scripts/security_audit.py --help`.
