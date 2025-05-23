import discord
from discord.ext import commands
from discord import app_commands
import time
import concurrent.futures
from datetime import datetime
import tls_client
import os

# Bot setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
THREADS = 40
token = ""
# Checker class
class Utils:
    def __init__(self) -> None:
        pass

    def calculateTimeRemaining(self, date):
        date = datetime.strptime(date.split("T")[0], '%Y-%m-%d')
        current_date = datetime.now()
        time_remaining = date - current_date
        days = time_remaining.days
        return f"{days} day"

    def format_credential(self, credential):
        parts = credential.split(':')
        if len(parts) == 3:
            return parts
        else:
            return None

class Checker:
    def __init__(self) -> None:
        self.utils = Utils()
        self.sp = 'eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIiwiZGV2aWNlIjoiIiwic3lzdGVtX2xvY2FsZSI6ImVuLVVTIiwiYnJvd3Nlcl91c2VyX2FnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyMC4wLjAuMCBTYWZhcmkvNTM3LjM2IiwiYnJvd3Nlcl92ZXJzaW9uIjoiMTIwLjAuMC4wIiwib3NfdmVyc2lvbiI6IjEwIiwicmVmZXJyZXIiOiIiLCJyZWZlcnJpbmdfZG9tYWluIjoiIiwicmVmZXJyZXJfY3VycmVudCI6IiIsInJlZmVycmluZ19kb21haW5fY3VycmVudCI6IiIsInJlbGVhc2VfY2hhbm5lbCI6InN0YWJsZSIsImNsaWVudF9idWlsZF9udW1iZXIiOjI1NjIzMSwiY2xpZW50X2V2ZW50X3NvdXJjZSI6bnVsbH0='
        self.requests = tls_client.Session(client_identifier="chrome120", random_tls_extension_order=True)

    def checkBoostsInToken(self, headers, proxy=None):
        boosts = 0
        request = self.requests.get('https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots', headers=headers, proxy=proxy)
        if request.status_code == 200:
            js = request.json()
            for boost in js:
                if not boost["cooldown_ends_at"]:
                    boosts += 1
        return boosts

    def check(self, credential, proxy=None):
        token_parts = self.utils.format_credential(credential)
        if not token_parts:
            return {"status": "Invalid", "message": "Invalid credential format. Expected email:pass:token."}
        email, password, token = token_parts
        headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'authorization': token,
            'referer': 'https://discord.com/channels/@me',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-debug-options': 'bugReporterEnabled',
            'x-discord-locale': 'en-US',
            'x-super-properties': self.sp,
        }
        try:
            request = self.requests.get(f'https://discord.com/api/v9/users/@me/billing/subscriptions', headers=headers, proxy=proxy)
            statusCode = request.status_code
            if statusCode == 401:
                return {"status": "Locked", "message": f"{credential[:20]}**** | Status: LOCKED"}
            if statusCode == 429:
                return {"status": "Ratelimited", "message": f"{credential[:20]}**** | Ratelimited"}
            if statusCode == 200:
                js = request.json()
                hasNitro = len(js) != 0
                nitroTime = self.utils.calculateTimeRemaining(js[0]["current_period_end"]) if hasNitro else "N/A"
                boosts = self.checkBoostsInToken(headers, proxy)
                return {
                    "status": "Unlocked",
                    "message": f"{credential[:20]}**** | Status: UNLOCKED, Nitro: {'YES' if hasNitro else 'NO'}, Subscription Expire in: {nitroTime}, Boosts left: {boosts}"
                }
            return {"status": "Invalid", "message": f"{credential[:20]}**** | Status: INVALID"}
        except Exception as e:
            return {"status": "Error", "message": f"Error checking {credential[:20]}****: {e}"}

checker = Checker()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    try:
        synced_commands = await bot.tree.sync()
        print(f"Slash commands synced successfully. {len(synced_commands)} command(s) registered.")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")

@bot.tree.command(name="check", description="Upload a file containing tokens to check them")
async def check(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith(".txt"):
        await interaction.response.send_message("Please upload a text file containing tokens.", ephemeral=True)
        return

    # Defer the response to allow for processing time
    await interaction.response.defer(ephemeral=True)

    # Download the file
    file_path = f"{file.filename}"
    await file.save(file_path)

    # Check tokens
    with open(file_path, "r") as f:
        credentials = f.read().splitlines()

    start = time.time()
    results = {"valid": [], "invalid": [], "locked": [], "ratelimited": [], "errors": []}

    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = [executor.submit(checker.check, credential) for credential in credentials]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result["status"] == "Ratelimited":
                results["ratelimited"].append(result["message"])
            elif result["status"] == "Locked":
                results["locked"].append(result["message"])
            elif result["status"] == "Invalid":
                results["invalid"].append(result["message"])
            elif result["status"] == "Error":
                results["errors"].append(result["message"])
            else:
                results["valid"].append(result["message"])

    end = time.time() - start
    os.remove(file_path)  # Clean up the file

    # Prepare result files
    result_files = {
        'valid_tokens.txt': '\n'.join(results["valid"]),
        'invalid_tokens.txt': '\n'.join(results["invalid"]),
        'locked_tokens.txt': '\n'.join(results["locked"]),
        'ratelimited_tokens.txt': '\n'.join(results["ratelimited"]),
        'errors.txt': '\n'.join(results["errors"]),
    }

    # Send results to the user
    user = interaction.user
    dm_channel = await user.create_dm()
    await dm_channel.send(f"Checked {len(credentials)} credentials in {end:.2f}s")

    for filename, content in result_files.items():
        file_path = f"{filename}"
        with open(file_path, "w") as f:
            f.write(content)
        await dm_channel.send(file=discord.File(file_path))
        os.remove(file_path)  # Clean up the temporary file

    # Send a final response to acknowledge that results have been sent
    await interaction.followup.send("Results have been sent to your DMs.", ephemeral=True)

bot.run("YOUR_BOT_TOKEN")
