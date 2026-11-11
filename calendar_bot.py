import discord
from discord.ext import commands, tasks
import os
import threading
from datetime import datetime, date, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==============================================================================
# 1. BACKGROUND WEB SERVER (Keep-Alive for Render)
# ==============================================================================
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Pizzin Calendar Bot is online and running 24/7!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==============================================================================
# 2. DISCORD BOT SETUP & CONFIGURATION
# ==============================================================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Updated to correct channel ID from user link
CALENDAR_CHANNEL_ID = 1563446765657657394  

# --- AUTHORIZED ADMINS & FLOATERS ---
ALLOWED_ADMINS = {
    # Executives & VPs
    723800522947166218,  # starfaii88 (President)
    1253326811882979329, # sweet_manis_ (VP)
    1400511932037070921, # aangel1325 (VP)
    1455238315405217893, # tequila_qyla (VP)
    626874233888440330,  # inesfgguerreiro (VP)
    967001330361192520,  # just2_peach (VP)
    1384881169547530291, # blossiq12 (VP)
    1527320411082068018, # fanaem00 (Executive / Nana)
    753681817776947282,  # renzoor145 (Executive)
    
    # Floaters
    741251553452752976,  # cyan143 (FLOATER)
    795323523132293160,  # gwendita_zai (FLOATER)
    1332012068798206073, # lincy_2003_73773 (FLOATER)
    848524697205342278,  # maxx_712 (FLOATER)
    837199088922787850,  # smolsanson (FLOATER)
    1322558573699403918, # soyoneul (FLOATER)
}

calendar_message_id = None
events_records = {}  

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
}

def parse_date_str(date_str):
    try:
        parts = date_str.strip().split()
        if len(parts) >= 3:
            day = int(parts[0])
            month_str = parts[1][:3].upper()
            year = int(parts[2])
            month = MONTH_MAP.get(month_str, 1)
            return date(year, month, day)
    except Exception:
        pass
    return None

def get_next_event_id():
    existing_ids = set(events_records.keys())
    candidate = 1
    while candidate in existing_ids:
        candidate += 1
    return candidate

@bot.event
async def on_ready():
    print(f"Pizzin Calendar Bot connected as {bot.user}")
    if not event_reminder_task.is_running():
        event_reminder_task.start()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

# ==============================================================================
# 3. BACKGROUND TASK: COUNTDOWN REMINDERS & AUTO-CLEANUP
# ==============================================================================
@tasks.loop(hours=24)
async def event_reminder_task():
    global events_records
    if not events_records:
        return
    
    today = date.today()
    expired_ids = []
    
    for eid, data in events_records.items():
        parsed_date = parse_date_str(data["date"])
        if parsed_date:
            delta_days = (parsed_date - today).days
            role_ping = f"<@&{data['role_id']}>" if data.get('role_id') else ""
            host_display = f"<@{data['host_id']}>" if data.get('host_id') else "TBA"
            
            # 2 Days Before Reminder
            if delta_days == 2:
                for guild in bot.guilds:
                    channel = guild.get_channel(CALENDAR_CHANNEL_ID)
                    if channel:
                        await channel.send(
                            f"⏳ **[REMINDER: 2 DAYS LEFT]** {role_ping}\n"
                            f"> 📌 **{data['title']}** `[{data['category']}]`\n"
                            f"> 👤 **Event Host:** {host_display}\n"
                            f"> 🕒 Date: **{data['date']}** at `{data['time']}`\n"
                            f"> 💬 *{data['desc']}*"
                        )
            
            # 1 Day Before Reminder
            elif delta_days == 1:
                for guild in bot.guilds:
                    channel = guild.get_channel(CALENDAR_CHANNEL_ID)
                    if channel:
                        await channel.send(
                            f"⚠️ **[REMINDER: TOMORROW]** {role_ping}\n"
                            f"> 📌 **{data['title']}** `[{data['category']}]`\n"
                            f"> 👤 **Event Host:** {host_display}\n"
                            f"> 🕒 Time: `{data['time']}`\n"
                            f"> 💬 *{data['desc']}*"
                        )
            
            # Event Day Reminder
            elif delta_days == 0:
                for guild in bot.guilds:
                    channel = guild.get_channel(CALENDAR_CHANNEL_ID)
                    if channel:
                        await channel.send(
                            f"🚨 **[EVENT STARTING TODAY!]** {role_ping}\n"
                            f"> 📌 **{data['title']}** `[{data['category']}]`\n"
                            f"> 👤 **Event Host:** {host_display}\n"
                            f"> 🕒 Time Slot: `{data['time']}`\n"
                            f"> 💬 *{data['desc']}*"
                        )
            
            # Expired Event Cleanup
            if parsed_date < today:
                expired_ids.append(eid)
                
    if expired_ids:
        for eid in expired_ids:
            events_records.pop(eid, None)
                
        for guild in bot.guilds:
            channel = guild.get_channel(CALENDAR_CHANNEL_ID)
            if channel:
                await update_calendar_board(guild)
                break

# ==============================================================================
# 4. CALENDAR BOARD RENDERER
# ==============================================================================
async def update_calendar_board(guild):
    global calendar_message_id
    channel = guild.get_channel(CALENDAR_CHANNEL_ID)
    if not channel:
        return

    embed = discord.Embed(
        title="🗓️  P.I.Z.Z.I.N  •  EVENT CALENDAR", 
        color=discord.Color.from_rgb(255, 193, 7)
    )
    
    if not events_records:
        embed.description = "```yaml\n✨ No upcoming events scheduled at the moment. Stay tuned for future community highlights!\n```"
    else:
        events_lines = []
        sorted_events = sorted(
            events_records.items(), 
            key=lambda x: parse_date_str(x[1]["date"]) or date.max
        )
        
        today = date.today()
        for eid, data in sorted_events:
            ev_date = parse_date_str(data["date"])
            
            if ev_date == today:
                status_badge = "🟢 **[TODAY]**"
            elif ev_date and ev_date > today:
                status_badge = "⏳ **[UPCOMING]**"
            else:
                status_badge = "📌"

            category = data.get('category', 'EVENT')
            role_display = f"<@&{data['role_id']}>" if data.get('role_id') else "None"
            host_display = f"<@{data['host_id']}>" if data.get('host_id') else "TBA"
            
            events_lines.append(f"{status_badge} **[{data['date']}]**  •  ` 🕒 {data['time']} `  *(ID: `{eid}`)*")
            events_lines.append(f"> ✨ **{data['title']}** `[{category}]`")
            events_lines.append(f"> 👤 **Host:** {host_display}  |  🎯 **Target:** {role_display}")
            if data['desc']:
                events_lines.append(f"> 💬 *{data['desc']}*")
            events_lines.append("────────────────────────────────────────")
            
        embed.description = "\n".join(events_lines)

    embed.set_footer(text="🔒 Security Protocol: Restricted access exclusively to verified Pizzin Administrators & Floaters.")

    if calendar_message_id:
        try:
            msg = await channel.fetch_message(calendar_message_id)
            await msg.edit(embed=embed)
            return
        except discord.NotFound:
            pass
            
    msg = await channel.send(embed=embed)
    calendar_message_id = msg.id

# ==============================================================================
# 5. SECURED SLASH COMMANDS
# ==============================================================================
@bot.tree.command(name="add_event", description="[Admin/Floater] Register a new community event")
async def add_event(
    interaction: discord.Interaction, 
    date: str, 
    time_slot: str, 
    title: str, 
    host_admin: discord.Member, 
    ping_role: discord.Role = None, 
    category: str = "COMMUNITY", 
    description: str = "Official details will be announced shortly."
):
    await interaction.response.defer(ephemeral=True)
    
    if interaction.user.id not in ALLOWED_ADMINS:
        await interaction.followup.send("❌ **Access Denied:** You do not have the required administrative clearance to modify the calendar.", ephemeral=True)
        return

    eid = get_next_event_id()
    events_records[eid] = {
        "date": date.upper(),
        "time": time_slot.upper(),
        "title": title,
        "host_id": host_admin.id,
        "role_id": ping_role.id if ping_role else None,
        "category": category.upper(),
        "desc": description
    }

    await interaction.followup.send(f"✅ Event successfully registered! Assigned Reference ID: `{eid}` (Host: {host_admin.display_name})", ephemeral=True)
    await update_calendar_board(interaction.guild)

@bot.tree.command(name="delete_event", description="[Admin/Floater] Purge an existing event from the master calendar")
async def delete_event(interaction: discord.Interaction, event_id: int):
    await interaction.response.defer(ephemeral=True)
    
    if interaction.user.id not in ALLOWED_ADMINS:
        await interaction.followup.send("❌ **Access Denied:** You do not have the required administrative clearance to purge calendar entries.", ephemeral=True)
        return
        
    if event_id not in events_records:
        await interaction.followup.send("❌ **Error:** The specified Event ID does not exist in the records.", ephemeral=True)
        return
        
    deleted = events_records.pop(event_id)
    await interaction.followup.send(f"🗑️ Successfully removed Event ID `{event_id}` (*{deleted['title']}*) from the calendar.", ephemeral=True)
    await update_calendar_board(interaction.guild)

@bot.command()
async def setup_calendar(ctx):
    if ctx.author.id in ALLOWED_ADMINS:
        await update_calendar_board(ctx.guild)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

# ==============================================================================
# 6. RUN BOT
# ==============================================================================
bot.run(os.environ.get("DISCORD_TOKEN"))
