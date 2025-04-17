import os
import json
import asyncio
import logging
import requests
from logging.handlers import RotatingFileHandler
from pyrogram import Client, filters
from pyrogram.types import Message
from pyromod import listen
from details import api_id, api_hash, bot_token

# Logger Setup
LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[
        RotatingFileHandler("log.txt", maxBytes=5000000, backupCount=10),
        logging.StreamHandler(),
    ],
)

# Classplus API URL
API_URL = 'https://api.classplusapp.com/v2'

# Create assets folder if not exists
if not os.path.exists("assets"):
    os.makedirs("assets")

# Helper functions
def get_datetime_str():
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def create_html_file(file_path, course_name, content_list):
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f"<h1>{course_name}</h1>\n<ul>\n")
        for item in content_list:
            f.write(f"<li>{item}</li>\n")
        f.write("</ul>")

def get_course_content(session, course_id, folder_id=0):
    fetched_contents = []
    params = {
        'courseId': course_id,
        'folderId': folder_id,
    }
    res = session.get(f'{API_URL}/course/content/get', params=params)
    if res.status_code == 200:
        res = res.json()
        contents = res['data']['courseContent']
        for content in contents:
            if content['contentType'] == 1:
                sub_contents = get_course_content(session, course_id, content['id'])
                fetched_contents += sub_contents
            else:
                name = content.get('name')
                url = content.get('url')
                fetched_contents.append(f'{name}: {url}')
    return fetched_contents

# Pyrogram Client
bot = Client(
    "classplus_bot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token
)

# /start Command
@bot.on_message(filters.command(["start"]) & filters.private)
async def start(bot, message: Message):
    await message.reply_text(
        "**Hi! I am Classplus TXT Downloader Bot.**\n\n"
        "Press /classplus to continue..."
    )

# /classplus Command
@bot.on_message(filters.command(["classplus"]) & filters.private)
async def classplus_handler(bot, message: Message):
    try:
        await message.reply_text(
            "**Send your credentials:**\n\n"
            "`Org Code`\n"
            "`Phone Number`\n\n"
            "OR\n\n"
            "`Access Token`\n\n"
            "**Send in one message.**"
        )
        creds = await bot.listen(message.chat.id)
        creds = creds.text.strip()

        session = requests.Session()
        headers = {
            'accept-encoding': 'gzip',
            'accept-language': 'EN',
            'api-version': '35',
            'app-version': '1.4.73.2',
            'build-number': '35',
            'connection': 'Keep-Alive',
            'content-type': 'application/json',
            'device-details': 'Xiaomi_Redmi 7_SDK-32',
            'device-id': 'c28d3cb16bbdac01',
            'host': 'api.classplusapp.com',
            'region': 'IN',
            'user-agent': 'Mobile-Android',
            'webengage-luid': '00000187-6fe4-5d41-a530-26186858be4c'
        }
        session.headers.update(headers)

        logged_in = False

        if '\n' in creds:
            org_code, phone_no = [x.strip() for x in creds.split('\n')]
            if org_code.isalpha() and phone_no.isdigit() and len(phone_no) == 10:
                res = session.get(f'{API_URL}/orgs/{org_code}')
                if res.status_code == 200:
                    org_id = res.json()['data']['orgId']
                    data = {
                        'countryExt': '91',
                        'mobile': phone_no,
                        'viaSms': 1,
                        'orgId': org_id,
                        'eventType': 'login',
                        'otpHash': 'j7ej6eW5VO'
                    }
                    res = session.post(f'{API_URL}/otp/generate', json=data)
                    if res.status_code == 200:
                        session_id = res.json()['data']['sessionId']
                        otp_msg = await message.reply_text("**Send OTP:**")
                        otp = await bot.listen(message.chat.id)
                        otp = otp.text.strip()
                        verify_data = {
                            'otp': otp,
                            'sessionId': session_id,
                            'orgId': org_id,
                            'fingerprintId': 'a3ee05fbde3958184f682839be4fd0f7',
                            'countryExt': '91',
                            'mobile': phone_no,
                        }
                        res = session.post(f'{API_URL}/users/verify', json=verify_data)
                        if res.status_code == 200:
                            token = res.json()['data']['token']
                            session.headers['x-access-token'] = token
                            logged_in = True
                            await message.reply_text(f"**Access Token:**\n\n`{token}`")
        else:
            token = creds
            session.headers['x-access-token'] = token
            res = session.get(f'{API_URL}/users/details')
            if res.status_code == 200:
                logged_in = True

        if logged_in:
            res = session.get(f'{API_URL}/profiles/users/data', params={'tabCategoryId': 3})
            if res.status_code == 200:
                courses = res.json()['data']['responseData']['coursesData']
                if not courses:
                    await message.reply_text("No courses found.")
                    return

                course_list = "\n".join(f"{i+1}. {c['name']}" for i, c in enumerate(courses))
                ask_course = await message.reply_text(
                    "**Send course number to download:**\n\n" + course_list
                )
                course_no = await bot.listen(message.chat.id)
                course_no = int(course_no.text.strip())

                selected_course = courses[course_no - 1]
                selected_course_id = selected_course['id']
                selected_course_name = selected_course['name']

                loading = await message.reply_text("Extracting course contents...")

                contents = get_course_content(session, selected_course_id)

                if contents:
                    # Save TXT
                    txt_file = f'assets/{get_datetime_str()}.txt'
                    with open(txt_file, 'w', encoding='utf-8') as f:
                        for line in contents:
                            f.write(f"{line}\n")

                    # Save HTML
                    html_file = f'assets/{get_datetime_str()}.html'
                    create_html_file(html_file, selected_course_name, contents)

                    await bot.send_document(
                        message.chat.id,
                        txt_file,
                        caption=f"**{selected_course_name}** TXT File",
                        file_name=f"{selected_course_name}.txt"
                    )
                    await bot.send_document(
                        message.chat.id,
                        html_file,
                        caption=f"**{selected_course_name}** HTML File",
                        file_name=f"{selected_course_name}.html"
                    )

                    os.remove(txt_file)
                    os.remove(html_file)

                await loading.delete()

            else:
                await message.reply_text("Failed to get courses.")

    except Exception as e:
        LOGGER.error(str(e))
        await message.reply_text(f"Error: {e}")

# Start bot
bot.run()
