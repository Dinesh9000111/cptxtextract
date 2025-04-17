import os
import json
import requests
import asyncio
from pyrogram import Client, filters
from pyromod import listen

# Import your constants
from details import API_ID, API_HASH, BOT_TOKEN

# Classplus API base
api = 'https://api.classplusapp.com/v2'

# Create HTML file from content
def create_html_file(file_name, batch_name, contents):
    tbody = ''
    parts = contents.split('\n')
    for part in parts:
        split_part = [item.strip() for item in part.split(':', 1)]
        text = split_part[0] if split_part[0] else 'Untitled'
        url = split_part[1].strip() if len(split_part) > 1 and split_part[1].strip() else 'No URL'
        tbody += f'<tr><td>{text}</td><td><a href="{url}" target="_blank">{url}</a></td></tr>'

    with open('cptxtextract/template.html', 'r') as fp:
        template = fp.read()
    title = batch_name.strip()
    with open(file_name, 'w') as fp:
        fp.write(template.replace('{{tbody_content}}', tbody).replace('{{batch_name}}', title))

# Fetch course content recursively
def get_course_content(session, course_id, folder_id=0):
    fetched_contents = ""
    params = {
        'courseId': course_id,
        'folderId': folder_id,
    }
    res = session.get(f'{api}/course/content/get', params=params)
    if res.status_code == 200:
        res_json = res.json()
        contents = res_json.get('data', {}).get('courseContent', [])
        for content in contents:
            if content['contentType'] == 1:  # Folder
                resources = content.get('resources', {})
                if resources.get('videos') or resources.get('files'):
                    sub_contents = get_course_content(session, course_id, content['id'])
                    fetched_contents += sub_contents
            elif content['contentType'] == 2:  # Video
                name = content.get('name', '')
                content_id = content.get('contentHashId', '')
                headers = {
                    "Host": "api.classplusapp.com",
                    "User-Agent": "Mobile-Android",
                    "x-access-token": session.headers.get('x-access-token', ''),
                    "Origin": "https://web.classplusapp.com",
                    "Referer": "https://web.classplusapp.com/",
                    "Region": "IN",
                }
                params = {'contentId': content_id}
                r = session.get('https://api.classplusapp.com/cams/uploader/video/jw-signed-url', headers=headers, params=params)
                if r.status_code == 200:
                    url = r.json().get('url', '')
                    if url:
                        fetched_contents += f'{name}:{url}\n'
            else:  # PDF / Link
                name = content.get('name', '')
                url = content.get('url', '')
                fetched_contents += f'{name}:{url}\n'
    return fetched_contents

# Command Handler: /start
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text("Hi! Send /extract to begin extracting Classplus course content.")

# Command Handler: /extract
@app.on_message(filters.command("extract") & filters.private)
async def classplus_txt(app, message):
    headers = {
        "Api-Version": "43",
        "Content-Type": "application/json;charset=UTF-8",
        "Device-Id": "1706954623055",
        "Origin": "https://web.classplusapp.com",
        "Referer": "https://web.classplusapp.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0 Safari/537.36",
    }
    try:
        input = await app.ask(message.chat.id, "Send Credentials:\nORG CODE + PHONE NUMBER (OR only TOKEN)")

        creds = input.text.strip()
        session = requests.Session()
        session.headers.update(headers)

        logged_in = False

        if '\n' in creds:  # OrgCode + Phone
            org_code, phone_no = [c.strip() for c in creds.split('\n')]
            res = session.get(f'{api}/orgs/{org_code}')
            if res.status_code != 200:
                raise Exception("Invalid Org Code.")

            org_id = res.json()['data']['orgId']

            data = {
                'countryExt': '91',
                'mobile': phone_no,
                'orgCode': org_code,
                'orgId': org_id,
                'viaSms': 1,
            }
            otp_res = session.post(f'{api}/otp/generate', data=json.dumps(data))
            if otp_res.status_code != 200:
                raise Exception("OTP Generate Failed.")

            session_id = otp_res.json()['data']['sessionId']
            otp_input = await app.ask(message.chat.id, "Enter OTP:")
            otp = otp_input.text.strip()

            verify_data = {
                "otp": otp,
                "countryExt": "91",
                "sessionId": session_id,
                "orgId": org_id,
                "mobile": phone_no
            }
            verify_res = session.post(f'{api}/users/verify', data=json.dumps(verify_data))
            if verify_res.status_code != 200 or verify_res.json().get('status') != 'success':
                raise Exception("OTP Verification Failed.")

            token = verify_res.json()['data']['token']
            session.headers['x-access-token'] = token
            logged_in = True
        else:  # Access Token
            token = creds
            session.headers['x-access-token'] = token
            user_details = session.get(f'{api}/users/details')
            if user_details.status_code == 200:
                logged_in = True
            else:
                raise Exception("Invalid Token.")

        if logged_in:
            # Get User Courses
            user_id = session.get(f'{api}/users/details').json()['data']['responseData']['user']['id']
            params = {'userId': user_id, 'tabCategoryId': 3}
            courses_res = session.get(f'{api}/profiles/users/data', params=params)
            if courses_res.status_code != 200:
                raise Exception("Failed to fetch courses.")

            courses = courses_res.json()['data']['responseData']['coursesData']
            if not courses:
                raise Exception("No courses found.")

            text = ''
            for idx, course in enumerate(courses):
                text += f"{idx+1}. {course['name']}\n"

            selected = await app.ask(message.chat.id, f"Select course number:\n\n{text}")
            course_index = int(selected.text.strip()) - 1
            selected_course = courses[course_index]

            msg = await message.reply_text("Extracting, please wait...")

            # Fetch Course Content
            contents = get_course_content(session, selected_course['id'])

            if not contents:
                await msg.edit("No content found in course.")
                return

            course_name = selected_course['name']
            with open("Classplus.txt", "w") as f:
                f.write(contents)

            await app.send_document(message.chat.id, "Classplus.txt", caption=f"Course: {course_name}")

            create_html_file("Classplus.html", course_name, contents)
            await app.send_document(message.chat.id, "Classplus.html", caption=f"Course: {course_name}")

            os.remove("Classplus.txt")
            os.remove("Classplus.html")
            await msg.delete()
    except Exception as e:
        await message.reply_text(f"Error: {e}")
        print(f"Error: {e}")

# Initialize Bot
app = Client(
    "classplus_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Start
app.run()
