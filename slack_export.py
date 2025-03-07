from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import json
import argparse
import os
import shutil
from datetime import datetime
from pick import pick
from time import sleep
import requests

def getHistory(slack, channel_id, page_size=100):
    messages = []
    cursor = None
    while True:
        try:
            response = slack.conversations_history(
                channel=channel_id,
                limit=page_size,
                cursor=cursor,
                oldest="0"
            )
            messages.extend(response["messages"])
            if response["has_more"]:
                cursor = response["response_metadata"]["next_cursor"]
                sleep(1)
            else:
                break
        except SlackApiError as e:
            print(f"Error fetching history for {channel_id}: {e.response['error']}")
            break
    messages.sort(key=lambda message: message["ts"])
    return messages

def getCanvases(slack):
    """
    Retrieve canvas files using the files.list endpoint with page-based pagination.
    """
    canvases = []
    page = 1
    while True:
        try:
            response = slack.files_list(count=100, page=page, types="canvas")
            # print(f"Canvas API response (page {page}):", json.dumps(response.data, indent=2))
            current_canvases = response.get("files", [])
            canvases.extend(current_canvases)
            paging = response.get("paging", {})
            total_pages = paging.get("pages", 1)
            if page >= total_pages:
                break
            page += 1
            sleep(1)
        except SlackApiError as e:
            print(f"Error fetching canvases: {e.response['error']}")
            break
    return canvases

def getFiles(slack):
    """
    Retrieve non-canvas files using the files.list endpoint with page-based pagination.
    We explicitly request types that exclude canvases (which are returned separately) and
    pass show_files_hidden_by_limit to ensure we get files even if they’re hidden by export limits.
    """
    # Define a comma-separated list of file types you expect (adjust as needed)
    non_canvas_types = "images,snippets,gdocs,zips,pdfs"
    files = []
    page = 1
    while True:
        try:
            response = slack.files_list(count=100,
                                        page=page,
                                        types=non_canvas_types,
                                        show_files_hidden_by_limit=True)
            # print(f"Files API response (page {page}):", json.dumps(response.data, indent=2))
            current_files = response.get("files", [])
            files.extend(current_files)
            paging = response.get("paging", {})
            total_pages = paging.get("pages", 1)
            if page >= total_pages:
                break
            page += 1
            sleep(1)
        except SlackApiError as e:
            print(f"Error fetching files: {e.response['error']}")
            break
    return files

def exportFiles(slack, output_dir):
    files = getFiles(slack)
    files_dir = os.path.join(output_dir, "files")
    mkdir(files_dir)
    print(f"Found {len(files)} files to export")
    files_metadata = []
    for file in files:
        file_id = file["id"]
        # Prefer title over name, and fall back if needed
        name = file.get("title") or file.get("name") or f"file_{file_id}"
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-', '.')).strip()
        url = file.get("url_private_download")
        if not url:
            print(f"Skipping file {name} because no download URL is provided.")
            continue
        try:
            headers = {"Authorization": f"Bearer {slack.token}"}
            response = requests.get(url, headers=headers, stream=True)
            response.raise_for_status()
            file_path = os.path.join(files_dir, safe_name)
            base_name, ext = os.path.splitext(file_path)
            counter = 1
            while os.path.exists(file_path):
                file_path = f"{base_name}_{counter}{ext}"
                counter += 1
            with open(file_path, "wb") as f:
                response.raw.decode_content = True
                shutil.copyfileobj(response.raw, f)
            files_metadata.append({
                "id": file_id,
                "name": name,
                "file_path": file_path,
                "created": file.get("created"),
                "updated": file.get("timestamp"),
                "url_private_download": url,
                "filetype": file.get("filetype"),
                "size": file.get("size")
            })
            print(f"Exported file: {name}")
        except Exception as e:
            print(f"Error exporting file {name}: {str(e)}")
    with open(os.path.join(files_dir, "files.json"), "w") as f:
        json.dump(files_metadata, f, indent=4)

def exportCanvases(slack, output_dir):
    canvases = getCanvases(slack)
    canvas_dir = os.path.join(output_dir, "canvases")
    mkdir(canvas_dir)
    print(f"Found {len(canvases)} canvases to export")
    canvas_metadata = []
    for canvas in canvases:
        canvas_id = canvas["id"]
        title = canvas.get("title", f"canvas_{canvas_id}")
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
        url = canvas.get("url_private_download")
        if not url:
            print(f"Skipping canvas {title} because no download URL is provided.")
            continue
        try:
            headers = {"Authorization": f"Bearer {slack.token}"}
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            canvas_file = os.path.join(canvas_dir, f"{safe_title}_{canvas_id}.html")
            with open(canvas_file, "w", encoding="utf-8") as f:
                f.write(response.text)
            canvas_metadata.append({
                "id": canvas_id,
                "title": title,
                "file_path": canvas_file,
                "created": canvas.get("created"),
                "updated": canvas.get("updated"),
                "url_private_download": url
            })
            print(f"Exported canvas: {title}")
        except Exception as e:
            print(f"Error exporting canvas {title}: {str(e)}")
    with open(os.path.join(canvas_dir, "canvases.json"), "w") as f:
        json.dump(canvas_metadata, f, indent=4)

def mkdir(directory):
    if not os.path.isdir(directory):
        os.makedirs(directory)

def parseTimeStamp(timeStamp):
    if '.' in timeStamp:
        t_list = timeStamp.split('.')
        if len(t_list) != 2:
            raise ValueError('Invalid time stamp')
        else:
            return datetime.utcfromtimestamp(float(t_list[0]))

def channelRename(oldRoomName, newRoomName):
    if not os.path.isdir(oldRoomName):
        return
    mkdir(newRoomName)
    for fileName in os.listdir(oldRoomName):
        shutil.move(os.path.join(oldRoomName, fileName), newRoomName)
    os.rmdir(oldRoomName)

def writeMessageFile(fileName, messages):
    directory = os.path.dirname(fileName)
    if not messages:
        return
    if not os.path.isdir(directory):
        mkdir(directory)
    with open(fileName, 'w') as outFile:
        json.dump(messages, outFile, indent=4)

def parseMessages(roomDir, messages, roomType):
    nameChangeFlag = roomType + "_name"
    currentFileDate = ''
    currentMessages = []
    for message in messages:
        ts = parseTimeStamp(message['ts'])
        fileDate = '{:%Y-%m-%d}'.format(ts)
        if fileDate != currentFileDate:
            outFileName = f'{roomDir}/{currentFileDate}.json'
            writeMessageFile(outFileName, currentMessages)
            currentFileDate = fileDate
            currentMessages = []
        if roomType != "im" and ('subtype' in message) and message['subtype'] == nameChangeFlag:
            roomDir = message['name']
            oldRoomPath = message['old_name']
            newRoomPath = roomDir
            channelRename(oldRoomPath, newRoomPath)
        currentMessages.append(message)
    outFileName = f'{roomDir}/{currentFileDate}.json'
    writeMessageFile(outFileName, currentMessages)

def filterConversationsByName(channelsOrGroups, channelOrGroupNames):
    return [conversation for conversation in channelsOrGroups if conversation['name'] in channelOrGroupNames]

def promptForPublicChannels(channels):
    channelNames = [channel['name'] for channel in channels]
    selectedChannels = pick(channelNames, 'Select the Public Channels you want to export:', multi_select=True)
    return [channels[index] for channelName, index in selectedChannels]

def fetchPublicChannels(slack, channels):
    if dryRun:
        print("Public Channels selected for export:")
        for channel in channels:
            print(channel['name'])
        print()
        return
    for channel in channels:
        channel_dir = channel['name'].encode('utf-8')
        print(f"Fetching history for Public Channel: {channel_dir}")
        mkdir(channel_dir)
        try:
            messages = getHistory(slack, channel['id'])
            parseMessages(channel_dir, messages, 'channel')
        except SlackApiError as e:
            print(f"Skipping {channel['name']} due to error: {e.response['error']}")

def dumpChannelFile():
    global token_owner_id
    print("Making channels file")
    all_conversations = channels + [g for g in groups if not g['is_mpim']] + [g for g in groups if g['is_mpim']] + dms
    for dm in dms:
        dm['members'] = [dm['user'], token_owner_id]
    with open('channels.json', 'w') as outFile:
        json.dump(all_conversations, outFile, indent=4)

def filterDirectMessagesByUserNameOrId(dms, userNamesOrIds):
    userIds = [userIdsByName.get(userNameOrId, userNameOrId) for userNameOrId in userNamesOrIds]
    return [dm for dm in dms if dm['user'] in userIds]

def promptForDirectMessages(dms):
    dmNames = [userNamesById.get(dm['user'], dm['user'] + " (name unknown)") for dm in dms]
    selectedDms = pick(dmNames, 'Select the 1:1 DMs you want to export:', multi_select=True)
    return [dms[index] for dmName, index in selectedDms]

def fetchDirectMessages(slack, dms):
    if dryRun:
        print("1:1 DMs selected for export:")
        for dm in dms:
            print(userNamesById.get(dm['user'], dm['user'] + " (name unknown)"))
        print()
        return
    for dm in dms:
        name = userNamesById.get(dm['user'], dm['user'] + " (name unknown)")
        print(f"Fetching 1:1 DMs with {name}")
        dm_id = dm['id']
        mkdir(dm_id)
        try:
            messages = getHistory(slack, dm_id)
            parseMessages(dm_id, messages, "im")
        except SlackApiError as e:
            print(f"Skipping DM with {name} due to error: {e.response['error']}")

def promptForGroups(groups):
    groupNames = [group['name'] for group in groups]
    selectedGroups = pick(groupNames, 'Select the Private Channels and Group DMs you want to export:', multi_select=True)
    return [groups[index] for groupName, index in selectedGroups]

def fetchGroups(slack, groups):
    if dryRun:
        print("Private Channels and Group DMs selected for export:")
        for group in groups:
            print(group['name'])
        print()
        return
    for group in groups:
        group_dir = group['name'].encode('utf-8')
        print(f"Fetching history for Private Channel / Group DM: {group['name']}")
        mkdir(group_dir)
        try:
            messages = getHistory(slack, group['id'])
            parseMessages(group_dir, messages, 'group')
        except SlackApiError as e:
            print(f"Skipping {group['name']} due to error: {e.response['error']}")

def getUserMap():
    global userNamesById, userIdsByName
    for user in users:
        userNamesById[user['id']] = user['name']
        userIdsByName[user['name']] = user['id']

def dumpUserFile():
    with open("users.json", 'w') as userFile:
        json.dump(users, userFile, indent=4)

def doTestAuth(slack):
    try:
        test_auth = slack.auth_test()
        team_name = test_auth["team"]
        current_user = test_auth["user"]
        print(f"Successfully authenticated for team {team_name} and user {current_user}")
        return test_auth
    except SlackApiError as e:
        print(f"Authentication failed: {e.response['error']}")
        exit(1)

def bootstrapKeyValues(slack):
    global users, channels, groups, dms
    try:
        users_response = slack.users_list()
        users = users_response["members"]
        print(f"Found {len(users)} Users")
        sleep(1)
        conversations_response = slack.conversations_list(
            types="public_channel,private_channel,im,mpim",
            limit=1000
        )
        all_conversations = conversations_response["channels"]
        channels = [c for c in all_conversations if c.get("is_channel", False) and not c.get("is_private", False)]
        groups = [c for c in all_conversations if (c.get("is_group", False) or c.get("is_mpim", False)) and c.get("is_private", False)]
        dms = [c for c in all_conversations if c.get("is_im", False)]
        print(f"Found {len(channels)} Public Channels")
        sleep(1)
        print(f"Found {len(groups)} Private Channels or Group DMs")
        sleep(1)
        print(f"Found {len(dms)} 1:1 DM conversations\n")
        sleep(1)
        getUserMap()
    except SlackApiError as e:
        print(f"Error bootstrapping data: {e.response['error']}")
        exit(1)

def selectConversations(allConversations, commandLineArg, filter, prompt):
    global args
    if isinstance(commandLineArg, list) and len(commandLineArg) > 0:
        return filter(allConversations, commandLineArg)
    elif commandLineArg != None or not anyConversationsSpecified():
        if args.prompt:
            return prompt(allConversations)
        else:
            return allConversations
    else:
        return []

def anyConversationsSpecified():
    global args
    return args.publicChannels != None or args.groups != None or args.directMessages != None

def dumpDummyChannel():
    if not channels:
        print("No public channels available for dummy channel creation.")
        return
    channel_name = channels[0]['name']
    mkdir(channel_name)
    file_date = '{:%Y-%m-%d}'.format(datetime.today())
    out_file_name = f'{channel_name}/{file_date}.json'
    writeMessageFile(out_file_name, [])

def finalize():
    os.chdir('..')
    if zipName:
        shutil.make_archive(zipName, 'zip', outputDirectory, None)
        shutil.rmtree(outputDirectory)
    exit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Export Slack history, canvases, and files')
    parser.add_argument('--token', required=True, help="Slack API token")
    parser.add_argument('--zip', help="Name of a zip file to output as")
    parser.add_argument('-o', '--output', default=os.getcwd(), help="Output directory (default: current directory)")
    parser.add_argument('--dryRun', action='store_true', default=False, help="List the conversations that will be exported without fetching or writing history")
    parser.add_argument('--publicChannels', nargs='*', default=None, metavar='CHANNEL_NAME', help="Export the given Public Channels")
    parser.add_argument('--groups', nargs='*', default=None, metavar='GROUP_NAME', help="Export the given Private Channels / Group DMs")
    parser.add_argument('--directMessages', nargs='*', default=None, metavar='USER_NAME', help="Export 1:1 DMs with the given users")
    parser.add_argument('--prompt', action='store_true', default=False, help="Prompt you to select the conversations to export")

    args = parser.parse_args()

    users = []
    channels = []
    groups = []
    dms = []
    userNamesById = {}
    userIdsByName = {}

    slack = WebClient(token=args.token)
    test_auth = doTestAuth(slack)
    token_owner_id = test_auth['user_id']

    bootstrapKeyValues(slack)

    dryRun = args.dryRun
    zipName = args.zip

    base_output_dir = os.path.abspath(os.path.expanduser(args.output))
    mkdir(base_output_dir)
    outputDirectory = os.path.join(base_output_dir, "{0}-slack_export".format(datetime.today().strftime("%Y%m%d-%H%M%S")))
    mkdir(outputDirectory)
    os.chdir(outputDirectory)

    if not dryRun:
        dumpUserFile()
        dumpChannelFile()
        exportCanvases(slack, outputDirectory)
        exportFiles(slack, outputDirectory)

    selected_channels = selectConversations(channels, args.publicChannels, filterConversationsByName, promptForPublicChannels)
    selected_groups = selectConversations(groups, args.groups, filterConversationsByName, promptForGroups)
    selected_dms = selectConversations(dms, args.directMessages, filterDirectMessagesByUserNameOrId, promptForDirectMessages)

    if len(selected_channels) > 0:
        fetchPublicChannels(slack, selected_channels)
    if len(selected_groups) > 0:
        if len(selected_channels) == 0:
            dumpDummyChannel()
        fetchGroups(slack, selected_groups)
    if len(selected_dms) > 0:
        fetchDirectMessages(slack, selected_dms)

    finalize()
