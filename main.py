import discord
from discord.ext import commands
from discord import app_commands
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime
import asyncio
from flask import Flask
from threading import Thread
import os
import json

# ====== ป้องกัน Sleep ======
app = Flask('')

@app.route('/')
def home():
    return "KAIZEN Bot is alive!"

def run_web():
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)  # ใช้ Flask ตรง ๆ


Thread(target=run_web).start()

# ====== Discord Bot ======
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ====== Google Sheets ======
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
credentials_info = json.loads(os.getenv("CREDENTIALS_JSON"))
creds = Credentials.from_service_account_info(credentials_info, scopes=scope)
client = gspread.authorize(creds)
sheet = client.open("FinanceBot").sheet1

MENU_CHANNEL_ID = 1390714068058243193
REPORT_CHANNEL_ID = 1390771152351264948

# ====== View ปุ่ม ======
class TypeButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ไม่หมดอายุ!
        self.summary_message = None

    @discord.ui.button(label="📥 รายรับ", style=discord.ButtonStyle.green, custom_id="income")
    async def income_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.start_entry(interaction, "รายรับ")

    @discord.ui.button(label="📤 รายจ่าย", style=discord.ButtonStyle.red, custom_id="expense")
    async def expense_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.start_entry(interaction, "รายจ่าย")

    @discord.ui.button(label="🧹 ล้างประวัติ", style=discord.ButtonStyle.grey, custom_id="clearhistory")
    async def clearhistory_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
            return

        await interaction.response.send_message(
            "⚠️ คุณแน่ใจหรือไม่ว่าต้องการ **ล้างประวัติทั้งหมด**? พิมพ์ `ยืนยัน` ภายใน 20 วินาที เพื่อยืนยัน.",
            ephemeral=False
        )

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=20)
            if msg.content.strip().lower() == "ยืนยัน":
                sheet.batch_clear(["A2:D"])
                confirm = await interaction.followup.send("✅ ล้างประวัติเรียบร้อยแล้ว", ephemeral=False)
                await asyncio.sleep(5)
                await confirm.delete()
            else:
                cancel = await interaction.followup.send("❌ ยกเลิกการล้างประวัติ", ephemeral=False)
                await asyncio.sleep(5)
                await cancel.delete()
            await msg.delete()
            await interaction.delete_original_response()
        except asyncio.TimeoutError:
            timeout = await interaction.followup.send("⌛ หมดเวลา ยกเลิกการล้างประวัติ", ephemeral=False)
            await asyncio.sleep(5)
            await timeout.delete()
            await interaction.delete_original_response()

    async def update_summary_message(self):
        channel = bot.get_channel(REPORT_CHANNEL_ID)
        if channel is None:
            print("ไม่พบช่องสรุป")
            return

        records = sheet.get_all_records()
        total_income = 0.0
        total_expense = 0.0
        last_entries = []

        for row in records:
            try:
                amount = float(row.get('จำนวน', 0))
            except:
                amount = 0.0
            t = row.get('ประเภท', '')
            note = row.get('หมายเหตุ', '')
            date = row.get('วันที่', '')

            if t == "รายรับ":
                total_income += amount
            elif t == "รายจ่าย":
                total_expense += amount

            last_entries.append(f"{date} | {t} | {amount:,.2f} บาท | {note}")

        last_entries = last_entries[-5:]
        balance = total_income - total_expense

        embed = discord.Embed(title="สรุปรายรับรายจ่าย (อัปเดตล่าสุด)", color=0x00ff00)
        embed.add_field(name="รายรับรวม", value=f"{total_income:,.2f} บาท", inline=False)
        embed.add_field(name="รายจ่ายรวม", value=f"{total_expense:,.2f} บาท", inline=False)
        embed.add_field(name="เงินคงเหลือ", value=f"{balance:,.2f} บาท", inline=False)
        embed.add_field(name="5 รายการล่าสุด", value="\n".join(last_entries) if last_entries else "-", inline=False)

        try:
            if self.summary_message is None:
                self.summary_message = await channel.send(embed=embed)
            else:
                await self.summary_message.edit(embed=embed)
        except Exception as e:
            print(f"เกิดข้อผิดพลาดขณะอัปเดตข้อความสรุป: {e}")

    async def start_entry(self, interaction: discord.Interaction, selected_type: str):
        await interaction.response.send_message(
            f"คุณเลือก: {selected_type}\nกรุณาใส่จำนวนเงิน (ตัวเลขเท่านั้น):",
            ephemeral=False
        )

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=60)
            amount = float(msg.content.replace(',', ''))
        except ValueError:
            fail = await interaction.followup.send("❌ จำนวนเงินไม่ถูกต้อง กรุณาลองใหม่", ephemeral=False)
            await asyncio.sleep(5)
            await fail.delete()
            await interaction.delete_original_response()
            return
        except asyncio.TimeoutError:
            timeout = await interaction.followup.send("⌛ หมดเวลา กรุณาเริ่มใหม่", ephemeral=False)
            await asyncio.sleep(5)
            await timeout.delete()
            await interaction.delete_original_response()
            return

        prompt2 = await interaction.followup.send("ใส่หมายเหตุเพิ่มเติม (ถ้ามี):", ephemeral=False)

        try:
            note_msg = await bot.wait_for("message", check=check, timeout=120)
            note = note_msg.content
        except asyncio.TimeoutError:
            timeout2 = await interaction.followup.send("⌛ หมดเวลา กรุณาเริ่มใหม่", ephemeral=False)
            await asyncio.sleep(5)
            await timeout2.delete()
            await interaction.delete_original_response()
            return

        date = datetime.now().strftime("%Y-%m-%d %H:%M")
        sheet.append_row([date, selected_type, amount, note])

        confirm = await interaction.followup.send(
            f'✅ บันทึกแล้ว: {amount} บาท {selected_type} - {note}',
            ephemeral=False
        )

        try:
            await msg.delete()
            await note_msg.delete()
            await prompt2.delete()
            await asyncio.sleep(5)
            await confirm.delete()
            await interaction.delete_original_response()
        except:
            pass

        await self.update_summary_message()


# ====== Slash Commands ======
@tree.command(name="postmenu", description="โพสต์เมนูรายรับรายจ่ายในห้องเมนู")
async def postmenu(interaction: discord.Interaction):
    channel = bot.get_channel(MENU_CHANNEL_ID)
    if channel is None:
        await interaction.response.send_message("❌ ไม่พบช่องเมนู", ephemeral=True)
        return

    view = TypeButtonView()
    await channel.send("กรุณาเลือกประเภทที่ต้องการเพิ่ม:", view=view)
    await interaction.response.send_message("✅ ส่งเมนูแล้วในห้องเมนู", ephemeral=True)


@tree.command(name="summary", description="แสดงสรุปรายรับรายจ่าย")
async def summary(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    records = sheet.get_all_records()
    total_income = 0.0
    total_expense = 0.0
    last_entries = []

    for row in records:
        try:
            amount = float(row.get('จำนวน', 0))
        except:
            amount = 0.0
        t = row.get('ประเภท', '')
        note = row.get('หมายเหตุ', '')
        date = row.get('วันที่', '')

        if t == "รายรับ":
            total_income += amount
        elif t == "รายจ่าย":
            total_expense += amount

        last_entries.append(f"{date} | {t} | {amount:,.2f} บาท | {note}")

    last_entries = last_entries[-5:]
    balance = total_income - total_expense

    embed = discord.Embed(title="สรุปรายรับรายจ่าย", color=0x00ff00)
    embed.add_field(name="รายรับรวม", value=f"{total_income:,.2f} บาท", inline=False)
    embed.add_field(name="รายจ่ายรวม", value=f"{total_expense:,.2f} บาท", inline=False)
    embed.add_field(name="เงินคงเหลือ", value=f"{balance:,.2f} บาท", inline=False)
    embed.add_field(name="5 รายการล่าสุด", value="\n".join(last_entries) if last_entries else "-", inline=False)
    embed.add_field(name="Google Sheets", value=f"[เปิดดูรายละเอียด]({https://docs.google.com/spreadsheets/d/1NHWdhr9tixhoRqWcl3pmqYhFRkHYiepcmKEDoXA9ICA/edit?usp=sharing})", inline=False)

    channel = bot.get_channel(REPORT_CHANNEL_ID)
    # สร้างข้อความที่จะ mention role (ใส่ <@&ROLE_ID>)
    role_mention = f"<@&{1331677856484298924}>"

    if channel:
       await channel.send(content=role_mention, embed=embed)

    await interaction.followup.send("✅ ส่งสรุปแล้วที่ห้องสรุป", ephemeral=True)


# ====== Background Task ======
async def summary_task():
    await bot.wait_until_ready()
    channel = bot.get_channel(REPORT_CHANNEL_ID)
    if channel is None:
        print("ไม่พบช่องสรุป")
        return

    message = None
    while not bot.is_closed():
        records = sheet.get_all_records()
        total_income = 0.0
        total_expense = 0.0
        last_entries = []

        for row in records:
            try:
                amount = float(row.get('จำนวน', 0))
            except:
                amount = 0.0
            t = row.get('ประเภท', '')
            note = row.get('หมายเหตุ', '')
            date = row.get('วันที่', '')

            if t == "รายรับ":
                total_income += amount
            elif t == "รายจ่าย":
                total_expense += amount

            last_entries.append(f"{date} | {t} | {amount:,.2f} บาท | {note}")

        last_entries = last_entries[-5:]
        balance = total_income - total_expense

        embed = discord.Embed(title="สรุปรายรับรายจ่าย (อัปเดตอัตโนมัติ)", color=0x00ff00)
        embed.add_field(name="รายรับรวม", value=f"{total_income:,.2f} บาท", inline=False)
        embed.add_field(name="รายจ่ายรวม", value=f"{total_expense:,.2f} บาท", inline=False)
        embed.add_field(name="เงินคงเหลือ", value=f"{balance:,.2f} บาท", inline=False)
        embed.add_field(name="5 รายการล่าสุด", value="\n".join(last_entries) if last_entries else "-", inline=False)

        try:
            if message is None:
                message = await channel.send(embed=embed)
            else:
                await message.edit(embed=embed)
        except Exception as e:
            print(f"เกิดข้อผิดพลาด: {e}")

        await asyncio.sleep(300)

# ====== On Ready ======
@bot.event
async def on_ready():
    print(f'✅ Bot {bot.user} พร้อมแล้ว!')
    await tree.sync()

    # ⭐ Register View ใหม่ทุกครั้ง
    bot.add_view(TypeButtonView())

    menu_channel = bot.get_channel(MENU_CHANNEL_ID)
    if menu_channel:
        await menu_channel.send("กรุณาเลือกประเภทที่ต้องการเพิ่ม:", view=TypeButtonView())

    bot.loop.create_task(summary_task())

bot.run(os.getenv("DISCORD_TOKEN"))
