# Slack Exporter

A Python script to export Slack conversations, canvases, and files.

## Description

The `slack_export.py` script uses a Slack user token to export:

- Public Channels
- Private Channels
- Direct Messages (1:1 DMs)
- Multi-Person Messages (Group DMs)
- Canvases
- Files

This script retrieves all conversations your user participates in, downloads their complete message history, and saves each as separate JSON files. It also exports canvases and files you have access to into dedicated directories. Unlike Slack's official exporter, which only covers public channels, this tool provides a user-centric export, including private content you can see.

**Note**: Export capabilities may be limited by your Slack workspace’s plan (e.g., free plans restrict some historical data) or your user’s permissions.

Slack endorses this API usage for personal exports (see [Slack's API documentation](https://get.slack.help/hc/en-us/articles/204897248)):  
*"If you want to export the contents of your own private groups and direct messages, please see our API documentation."*

### Getting a Slack Token

To use this script, you need a Slack **user token** (starts with `xoxp-`). Legacy tokens are deprecated, so follow these steps to create a Slack app and obtain a user token:

1. **Create a Slack App**:
   - Go to [api.slack.com/apps](https://api.slack.com/apps) and click "Create New App".
   - Name it (e.g., "Slack Exporter") and select your workspace.

2. **Configure Permissions**:
   - Navigate to "OAuth & Permissions".
   - Under "User Token Scopes", add:
     - `channels:history` (public channel messages)
     - `groups:history` (private channel messages)
     - `im:history` (1:1 DMs)
     - `mpim:history` (group DMs)
     - `files:read` (files and canvases)
     - `users:read` (user info for names/IDs)
   - These scopes enable the script to access your conversations, files, and canvases.

3. **Install the App**:
   - Go to "Install App" and click "Install to Workspace".
   - Authorize as yourself (e.g., `ecochran76`).
   - Copy the **User OAuth Token** (`xoxp-...`) from "OAuth & Permissions".

4. **Use the Token**:
   - Pass it to the script with the `--token` argument.

#### Bot vs. User Tokens
- **User Tokens (`xoxp-`)**:
  - Act as you (e.g., `ecochran76`), exporting data you can see in Slack.
  - Include private channels, DMs, and files/canvases you have access to, based on your permissions.
  - **Required** for this script to export your full personal data.

- **Bot Tokens (`xoxb-`)**:
  - Represent a bot user tied to the app, not your account.
  - Limited to public channels and bot interactions unless invited to private conversations.
  - **Not suitable** here—using a bot token will omit private channels, DMs, and most user-specific files/canvases.

Ensure you use a user token (`xoxp-`) for complete exports.

---

## Credits

This project is a fork of [zach-snell/slack-export](https://github.com/zach-snell/slack-export). Many thanks to Zach Snell for the original implementation, which inspired and formed the basis for this enhanced version.

---

## Dependencies

Install the required Python packages:

```bash
pip install slack_sdk  # https://github.com/slackapi/python-slack-sdk
pip install pick       # https://github.com/wong2/pick
pip install requests   # For downloading files and canvases
```

---

## Usage

The script exports all conversations (public channels, private channels, group DMs, 1:1 DMs), canvases, and files your user can access by default, saving them to a directory named `<timestamp>-slack_export` (e.g., `20250303-172345-slack_export`). Use the flags below to customize the export process, filter conversations, or modify output behavior.

### Command-Line Flags

- **`--token TOKEN`**  
  - **Required**: The Slack user token (`xoxp-...`) obtained from your Slack app.
  - Example: `--token xoxp-123...`

- **`--zip ZIP_NAME`**  
  - Optional: Creates a zip archive of the export directory (e.g., `slack_export.zip`) and deletes the original folder after zipping.
  - Useful for compatibility with tools like `slack-export-viewer`.
  - Default: No zip file is created.
  - Example: `--zip my_export`

- **`-o, --output PATH`**  
  - Optional: Specifies the base directory where the export folder (`<timestamp>-slack_export`) is created.
  - Supports `~` for your home directory (e.g., `~/slack_backups` on Windows becomes `C:\Users\YourUsername\slack_backups`).
  - Default: Current working directory.
  - Example: `-o ~/slack_backups`

- **`--dryRun`**  
  - Optional: Lists all available conversations (public channels, private channels, group DMs, 1:1 DMs) your user can export without fetching or saving anything.
  - Useful for previewing what will be exported.
  - Default: Disabled (full export runs).
  - Example: `--dryRun`

- **`--publicChannels [CHANNEL_NAME ...]`**  
  - Optional: Exports public channels. Without names, exports all public channels you’re in; with names, filters to the specified channels.
  - Names are case-sensitive and must match exactly (e.g., `General`, not `general`).
  - Default: Exports all public channels unless filtered.
  - Example: `--publicChannels General Random`

- **`--groups [GROUP_NAME ...]`**  
  - Optional: Exports private channels and group DMs. Without names, exports all you’re in; with names, filters to the specified ones.
  - Names must match exactly (e.g., `my_private_channel` or `mpdm-user1--user2-1`).
  - Default: Exports all private channels and group DMs unless filtered.
  - Example: `--groups my_private_channel`

- **`--directMessages [USER_NAME ...]`**  
  - Optional: Exports 1:1 DMs. Without names, exports all your DMs; with names, filters to the specified users.
  - Uses Slack usernames (e.g., `jane_smith`), not display names.
  - Default: Exports all 1:1 DMs unless filtered.
  - Example: `--directMessages jane_smith john_doe`

- **`--prompt`**  
  - Optional: Opens an interactive menu to select conversations (public channels, private channels/group DMs, 1:1 DMs) to export.
  - If combined with `--publicChannels`, `--groups`, or `--directMessages` with names, those named items are exported automatically, and the prompt applies to the unspecified types.
  - Default: Disabled (exports all conversations unless filtered).
  - Example: `--prompt`

### Usage Examples

```bash
# Export everything (channels, DMs, canvases, files) to the current directory
python slack_export.py --token xoxp-123...

# Export everything and save to a custom directory
python slack_export.py --token xoxp-123... -o ~/slack_backups

# Export everything into a zip file
python slack_export.py --token xoxp-123... --zip slack_export

# Preview all exportable conversations without saving
python slack_export.py --token xoxp-123... --dryRun

# Export only specific public channels
python slack_export.py --token xoxp-123... --publicChannels General Random

# Export all private channels and group DMs to a custom directory
python slack_export.py --token xoxp-123... --groups -o ~/backups

# Export 1:1 DMs with specific users
python slack_export.py --token xoxp-123... --directMessages jane_smith john_doe

# Export all public channels and specific group DMs
python slack_export.py --token xoxp-123... --publicChannels --groups mpdm-user1--user2-1

# Export DMs with jane_smith and prompt for public channels
python slack_export.py --token xoxp-123... --directMessages jane_smith --publicChannels --prompt

# Prompt for all conversation types interactively
python slack_export.py --token xoxp-123... --prompt

# Export public/private channels (no DMs) into a zip file
python slack_export.py --token xoxp-123... --publicChannels --groups --zip channels_only
```

### Notes on Behavior
- **Default Behavior**: Without filtering flags (`--publicChannels`, `--groups`, `--directMessages`), all conversations, canvases, and files are exported unless `--prompt` is used to select manually.
- **Combining Flags**: Use multiple flags to export specific subsets (e.g., `--publicChannels --directMessages` skips private channels/group DMs).
- **Canvases and Files**: Always exported unless `--dryRun` is used, regardless of conversation filters.
- **Rate Limits**: The script includes `sleep(1)` between API calls to respect Slack’s rate limits, which may slow large exports.

---

## Credits

This project is a fork of [zach-snell/slack-export](https://github.com/zach-snell/slack-export). Many thanks to Zach Snell for the original implementation, which inspired and formed the basis for this enhanced version.

---

## Dependencies

Install the required Python packages:

```bash
pip install slack_sdk  # https://github.com/slackapi/python-slack-sdk
pip install pick       # https://github.com/wong2/pick
pip install requests   # For downloading files and canvases
```

---

## Output Structure

- `users.json`: List of workspace users.
- `channels.json`: Metadata for exported conversations.
- `<channel_name>/<date>.json`: Message history for each channel/DM, split by date.
- `canvases/canvases.json`: Metadata for exported canvases.
- `canvases/<canvas_title>_<id>.html`: Exported canvas files.
- `files/files.json`: Metadata for exported files.
- `files/<file_name>`: Exported files (e.g., PDFs, images).

---

## Recommended Tools

Pairs with `slack-export-viewer` for viewing exports:

```bash
pip install slack-export-viewer
slack-export-viewer -z slack_export.zip
```

---

## Limitations

- Requires a user token (`xoxp-`) with scopes like `channels:history`, `files:read`, etc.
- Exports are limited to what your user can access in Slack.
- Free Slack plans may restrict message history or file access.

---

## License

This script is provided as-is, with no guarantees of updates or support. See the original repository for licensing details: [zach-snell/slack-export](https://github.com/zach-snell/slack-export).
