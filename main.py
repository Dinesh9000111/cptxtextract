from utils import get_datetime_str, create_html_file
import requests
import json
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram import Client, filters

api = 'https://api.classplusapp.com/v2'

headers = {
    'accept-encoding': 'gzip',
    'accept-language': 'EN',
    'api-version'    : '35',
    'app-version'    : '1.4.73.2',
    'build-number'   : '35',
    'connection'     : 'Keep-Alive',
    'content-type'   : 'application/json',
    'device-details' : 'Xiaomi_Redmi 7_SDK-32',
    'device-id'      : 'c28d3cb16bbdac01',
    'host'           : 'api.classplusapp.com',
    'region'         : 'IN',
    'user-agent'     : 'Mobile-Android',
    'webengage-luid' : '00000187-6fe4-5d41-a530-26186858be4c'
}

client_data = {}

# Helper function to recursively fetch course content
def get_course_content(session, course_id, folder_id=0):
    fetched_contents = []

    params = {
        'courseId': course_id,
        'folderId': folder_id,
    }

    res = session.get(f'{api}/course/content/get', params=params)

    if res.status_code == 200:
        res = res.json()
        contents = res['data']['courseContent']

        for content in contents:
            if content['contentType'] == 1:
                resources = content['resources']
                if resources['videos'] or resources['files']:
                    sub_contents = get_course_content(session, course_id, content['id'])
                    fetched_contents += sub_contents
            else:
                name = content['name']
                url = content['url']
                fetched_contents.append(f'{name}: {url}')

    return fetched_contents

@Client.on_message(filters.private & filters.command(['classplus']))
async def classplus_login(client: Client, message: Message):
    session = requests.Session()
    session.headers.update(headers)

    await message.reply("**Send your Access Token or\nOrganisation Code + Phone Number (separated by new line)**")
    reply = await client.listen(message.chat.id)
    creds = reply.text.strip()

    try:
        if '\n' in creds:
            org_code, phone_no = creds.split('\n')
            org_code = org_code.strip()
            phone_no = phone_no.strip()

            res = session.get(f'{api}/orgs/{org_code}')
            res.raise_for_status()
            org_id = res.json()['data']['orgId']

            data = {
                "countryExt": "91",
                "mobile": phone_no,
                "viaSms": 1,
                "orgId": org_id,
                "eventType": "login",
                "otpHash": "j7ej6eW5VO"
            }
            res = session.post(f'{api}/otp/generate', data=json.dumps(data))
            res.raise_for_status()
            session_id = res.json()['data']['sessionId']

            await message.reply("**Send the OTP you received**")
            otp_reply = await client.listen(message.chat.id)
            otp = otp_reply.text.strip()

            data = {
                "otp": otp,
                "sessionId": session_id,
                "orgId": org_id,
                "fingerprintId": "a3ee05fbde3958184f682839be4fd0f7",
                "countryExt": "91",
                "mobile": phone_no
            }
            res = session.post(f'{api}/users/verify', data=json.dumps(data))
            res.raise_for_status()
            token = res.json()['data']['token']

            await message.reply(f"**Your Access Token is:**\n\n`{token}`")

            session.headers['x-access-token'] = token

        else:
            token = creds
            session.headers['x-access-token'] = token

        res = session.get(f'{api}/profiles/users/data', params={"tabCategoryId": 3})
        res.raise_for_status()
        courses = res.json()['data']['responseData']['coursesData']

        if not courses:
            return await message.reply("**No courses found in your account.**")

        buttons = []
        for idx, course in enumerate(courses):
            buttons.append([InlineKeyboardButton(f"{idx+1}. {course['name']}", callback_data=f"classplus_course_{course['id']}")])

        await message.reply(
            "**Select the course you want to download:**",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

        # Save session and courses temporarily
        client_data[message.chat.id] = {
            "session": session,
            "courses": {course['id']: course['name'] for course in courses}
        }

    except Exception as e:
        await message.reply(f"**Error:** `{e}`")

@Client.on_callback_query(filters.regex(r'^classplus_course_(\d+)$'))
async def download_course(client: Client, callback_query: CallbackQuery):
    course_id = int(callback_query.data.split('_')[-1])
    chat_id = callback_query.message.chat.id

    if chat_id not in client_data:
        return await callback_query.answer("Session expired. Please /classplus again.", show_alert=True)

    session = client_data[chat_id]['session']
    course_name = client_data[chat_id]['courses'][course_id]

    await callback_query.message.edit(f"**Extracting course `{course_name}`... Please wait...**")

    content = get_course_content(session, course_id)

    if not content:
        return await callback_query.message.edit("**No content found in selected course.**")

    file_name_txt = f"{course_name.replace(' ', '_')}_{get_datetime_str()}.txt"
    file_name_html = f"{course_name.replace(' ', '_')}_{get_datetime_str()}.html"

    file_path_txt = os.path.join("assets", file_name_txt)
    file_path_html = os.path.join("assets", file_name_html)

    os.makedirs("assets", exist_ok=True)

    with open(file_path_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(content))

    create_html_file(file_path_html, course_name, content)

    await client.send_document(
        chat_id,
        file_path_txt,
        caption=f"**Course: {course_name} (.txt file)**",
        file_name=file_name_txt
    )

    await client.send_document(
        chat_id,
        file_path_html,
        caption=f"**Course: {course_name} (.html file)**",
        file_name=file_name_html
    )

    os.remove(file_path_txt)
    os.remove(file_path_html)

    await callback_query.message.edit("**Course files sent successfully!**")
