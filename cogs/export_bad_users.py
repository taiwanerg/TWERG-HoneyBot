import io
import sqlite3

import discord
from discord import app_commands
from discord.ext import commands

from cogs.owner import is_user_trusted
from cogs.server_check import is_server_authorized


BAD_USERS_DB = "ryker_badusers.db"
OWNER_GUILD_IDS = (518699949500661760, 897116721159233576)


class BadUsersExportCog(commands.Cog):
    """將 bad_users 惡意帳號庫匯出為每行一個純數字 ID 的 TXT 檔案。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _load_bad_user_ids() -> list[int]:
        with sqlite3.connect(BAD_USERS_DB) as conn:
            rows = conn.execute("SELECT user_id FROM bad_users").fetchall()

        return sorted({int(row[0]) for row in rows if str(row[0]).isdigit()})

    @app_commands.command(
        name="匯出惡意用戶",
        description="[擁有者/信任者] 將惡意用戶 ID 匯出為純數字 TXT 檔案",
    )
    @app_commands.guilds(*OWNER_GUILD_IDS)
    async def export_bad_users(self, interaction: discord.Interaction):
        if not is_server_authorized(interaction.guild_id):
            await interaction.response.send_message(
                "❌ 本伺服器尚未獲得機器人擁有者授權許可，無法使用此指令。",
                ephemeral=True,
            )
            return

        if not is_user_trusted(interaction.user.id):
            await interaction.response.send_message(
                "❌ 你不是「信任的人」，沒有權限匯出惡意用戶清單！",
                ephemeral=True,
            )
            return

        try:
            user_ids = self._load_bad_user_ids()
        except sqlite3.Error as error:
            await interaction.response.send_message(
                f"⚠️ 讀取惡意帳號資料庫失敗：{error}",
                ephemeral=True,
            )
            return

        if not user_ids:
            await interaction.response.send_message(
                "ℹ️ 目前沒有可匯出的惡意用戶 ID。",
                ephemeral=True,
            )
            return

        # 檔案內容只包含阿拉伯數字與換行字元。
        content = "\n".join(str(user_id) for user_id in user_ids)
        attachment = discord.File(
            io.BytesIO(content.encode("ascii")),
            filename="bad_users.txt",
        )
        await interaction.response.send_message(
            f"✅ 已匯出 `{len(user_ids)}` 個惡意用戶 ID。",
            file=attachment,
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(BadUsersExportCog(bot))
