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

This script retrieves all conversations your user participates in, downloads their complete history, and saves each conversation as separate JSON files. It also exports canvases and files to dedicated directories. Unlike Slack's official exporter, which only covers public channels, this tool provides a user-centric export, including private content you have access to.

**Note**: Export capabilities may be limited by your Slack workspace's paid status or user permissions.

Slack endorses this API usage for personal exports (see [Slack's API documentation](https://get.slack.help/hc/en-us/articles/204897248)):  
"If you want to export the contents of your own private groups and direct messages, please see our API documentation."

To obtain a user token (`xoxp-`), visit:  
[https://api.slack.com/custom-integrations/legacy-tokens](https://api.slack.com/custom-integrations/legacy-tokens)

---

## Credits

This project is a fork of [zach-snell/slack-export](https://github.com/zach-snell/slack-export). Many thanks to Zach Snell for the original implementation, which served as the foundation for this version.

---

## Dependencies

Install the required Python packages:

```bash
pip install slack_sdk  # https://github.com/slackapi/python-slack-sdk
pip install pick       # https://github.com/wong2/pick
pip install requests   # For downloading files and canvases
```

---

## Basic Usage

```bash
# Export all Channels, DMs, canvases, and files
python slack_export.py --token xoxp-123...

# List available Channels and DMs without exporting
python slack_export.py --token xoxp-123... --dryRun

# Prompt to select Channels and DMs to export
python slack_export.py --token xoxp-123... --prompt

# Export to a zip file (e.g., for slack-export-viewer)
python slack_export.py --token xoxp-123... --zip slack_export
```

Output is saved to a directory named `<timestamp>-slack_export` in the specified output path (default: current directory).

---

## Selecting Conversations to Export

By default, the script exports **all** conversations, canvases, and files your user can access. Use these arguments to filter:

- `--publicChannels [CHANNEL_NAME [CHANNEL_NAME ...]]`  
  Export Public Channels (optionally filtered by names).

- `--groups [GROUP_NAME [GROUP_NAME ...]]`  
  Export Private Channels and Group DMs (optionally filtered by names).

- `--directMessages [USER_NAME [USER_NAME ...]]`  
  Export 1:1 DMs (optionally filtered by usernames).

- `--prompt`  
  Interactively select conversations to export (overrides defaults unless other filters are specified).

### Examples

```bash
# Export only Public Channels
python slack_export.py --token xoxp-123... --publicChannels

# Export only "General" and "Random" Public Channels
python slack_export.py --token xoxp-123... --publicChannels General Random

# Export only Private Channels and Group DMs
python slack_export.py --token xoxp-123... --groups

# Export only the "my_private_channel" Private Channel
python slack_export.py --token xoxp-123... --groups my_private_channel

# Export only 1:1 DMs
python slack_export.py --token xoxp-123... --directMessages

# Export 1:1 DMs with jane_smith and john_doe
python slack_export.py --token xoxp-123... --directMessages jane_smith john_doe

# Export Public and Private Channels/Group DMs (no 1:1 DMs)
python slack_export.py --token xoxp-123... --publicChannels --groups

# Export DMs with jane_smith and prompt for Public Channels
python slack_export.py --token xoxp-123... --directMessages jane_smith --publicChannels --prompt
```

---

## Output Structure

- `users.json`: List of users in the workspace.
- `channels.json`: Metadata for all exported conversations.
- `<channel_name>/<date>.json`: Message history for each channel/DM, split by date.
- `canvases/canvases.json`: Metadata for exported canvases.
- `canvases/<canvas_title>_<id>.html`: Exported canvas files.
- `files/files.json`: Metadata for exported files.
- `files/<file_name>`: Exported files (e.g., PDFs, images).

---

## Recommended Tools

This script pairs well with `slack-export-viewer` for viewing exported data:

```bash
pip install slack-export-viewer
slack-export-viewer -z slack_export.zip
```

---

## Limitations

- Requires a legacy user token (`xoxp-`) with appropriate scopes (e.g., `channels:history`, `files:read`).
- Export scope is limited to what your user can access.
- Free Slack plans may restrict history or file access.

---

## License

This script is provided as-is, with no guarantees of updates or support. See the original repository for licensing details: [zach-snell/slack-export](https://github.com/zach-snell/slack-export).
