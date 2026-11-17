import discord
from discord.ext import commands
from discord import app_commands
import datetime
import re
import sqlite3
from cogs.owner import is_user_trusted
from cogs.server_check import is_server_authorized
from settings.settings_utils import (
    add_custom_bad_word,
    remove_custom_bad_word,
    list_custom_bad_words_detail,
    add_custom_regex_pattern,
    remove_custom_regex_pattern,
    list_custom_regex_patterns_detail,
)

# -------------------------------------------------------
# 自訂敏感詞管理 Cog (單一 /詞庫 指令)
# -------------------------------------------------------

class BadWordCog(commands.Cog):
    """動態自訂敏感詞庫管理 Cog"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="詞庫", description="[管理員/信任者] 管理敏感詞庫（新增 / 移除 / 列表 / 全域管理）")
    @app_commands.describe(
        操作="要執行的動作（新增、移除、列表、全域管理）",
        詞彙="要新增或移除的詞彙（查看列表時可不填）"
    )
    @app_commands.choices(操作=[
        app_commands.Choice(name="➕ 新增 (本伺服器)", value="add"),
        app_commands.Choice(name="➖ 移除 (本伺服器)", value="remove"),
        app_commands.Choice(name="📋 列表 (查看詞庫清單)", value="list"),
        app_commands.Choice(name="🌐 新增全域 (信任者 / 擁有者)", value="add_global"),
        app_commands.Choice(name="🗑️ 移除全域 (信任者 / 擁有者)", value="remove_global"),
    ])
    async def badword_command(
        self,
        interaction: discord.Interaction,
        操作: app_commands.Choice[str],
        詞彙: str = None
    ):
        # 1. 檢查伺服器授權
        if not is_server_authorized(interaction.guild_id):
            await interaction.response.send_message(
                "❌ 此伺服器尚未獲得機器人授權，無法使用此功能。", ephemeral=True
            )
            return

        # 2. 檢查使用者權限（伺服器管理員 或 信任者）
        is_admin = interaction.user.guild_permissions.administrator if isinstance(interaction.user, discord.Member) else False
        is_trusted = is_user_trusted(interaction.user.id)

        if not (is_admin or is_trusted):
            await interaction.response.send_message(
                "❌ 你沒有權限使用此指令！（需要伺服器管理員或機器人信任者權限）", ephemeral=True
            )
            return

        action = 操作.value
        word = (詞彙 or "").strip()

        # 2. 列表功能 (無需詞彙參數)
        if action == "list":
            words = list_custom_bad_words_detail(str(interaction.guild_id))
            if not words:
                await interaction.response.send_message(
                    "📋 目前全域及本伺服器詞庫皆無敏感詞。",
                    ephemeral=True
                )
                return

            global_words = [w for w in words if w["scope"] == "全域"]
            server_words = [w for w in words if w["scope"] == "本伺服器"]

            embeds = []
            for scope, entries in (("全域", global_words), ("本伺服器", server_words)):
                if not entries:
                    continue
                pages = []
                page = ""
                for entry in entries:
                    line = f"`{entry['word']}` — 由 {entry['added_by']}\n"
                    if len(page) + len(line) > 3500:
                        pages.append(page)
                        page = ""
                    page += line
                if page:
                    pages.append(page)
                for index, description in enumerate(pages, 1):
                    embed = discord.Embed(
                        title=f"📋 {scope}敏感詞庫（{len(entries)} 筆）— {index}/{len(pages)}",
                        description=description,
                        color=discord.Color.blurple(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.set_footer(text="敏感詞與正則皆由 DB 管理；正則請使用 /正則")
                    embeds.append(embed)

            await interaction.response.send_message(embed=embeds[0], ephemeral=True)
            for embed in embeds[1:]:
                await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 3. 其他操作需要詞彙參數
        if not word:
            await interaction.response.send_message(
                f"❌ 執行「{操作.name}」操作時，必須填寫 `詞彙` 參數！",
                ephemeral=True
            )
            return

        if len(word) > 100:
            await interaction.response.send_message("❌ 詞彙長度不可超過 100 字元。", ephemeral=True)
            return

        added_by = f"{interaction.user.display_name} ({interaction.user.id})"

        # 4. 新增至本伺服器
        if action == "add":
            success = add_custom_bad_word(str(interaction.guild_id), word, added_by)
            if success:
                embed = discord.Embed(
                    title="✅ 自訂敏感詞新增成功",
                    description=f"詞彙 `{word}` 已加入本伺服器詞庫，即時生效。",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.utcnow()
                )
                embed.set_footer(text=f"新增者：{interaction.user.display_name}")
                print(f"📝 [BadWord] 新增伺服器詞彙: '{word}' by {added_by} in guild {interaction.guild_id}")
            else:
                embed = discord.Embed(
                    title="⚠️ 詞彙已存在",
                    description=f"詞彙 `{word}` 已在本伺服器詞庫或全域詞庫中，無需重複新增。",
                    color=discord.Color.orange()
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # 5. 從本伺服器移除
        elif action == "remove":
            success = remove_custom_bad_word(str(interaction.guild_id), word)
            if success:
                embed = discord.Embed(
                    title="🗑️ 自訂敏感詞移除成功",
                    description=f"詞彙 `{word}` 已從本伺服器詞庫移除。",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.utcnow()
                )
                print(f"🗑️ [BadWord] 移除伺服器詞彙: '{word}' by {interaction.user} in guild {interaction.guild_id}")
            else:
                embed = discord.Embed(
                    title="❌ 詞彙不存在",
                    description=f"詞彙 `{word}` 不在本伺服器詞庫中。\n（注意：全域詞彙請由 Bot 擁有者選擇「移除全域」進行移除。）",
                    color=discord.Color.red()
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # 6. 新增全域 (Bot 擁有者)
        elif action == "add_global":
            if not is_user_trusted(interaction.user.id):
                await interaction.response.send_message("❌ 此操作僅限 Bot 擁有者使用。", ephemeral=True)
                return

            success = add_custom_bad_word("GLOBAL", word, added_by)
            if success:
                embed = discord.Embed(
                    title="✅ 全域敏感詞新增成功",
                    description=f"詞彙 `{word}` 已加入**全域詞庫**，即時對所有伺服器生效。",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.utcnow()
                )
                embed.set_footer(text=f"新增者：{interaction.user.display_name}")
                print(f"🌐 [BadWord] 新增全域詞彙: '{word}' by {added_by}")
            else:
                embed = discord.Embed(
                    title="⚠️ 詞彙已存在",
                    description=f"詞彙 `{word}` 已在全域詞庫中。",
                    color=discord.Color.orange()
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # 7. 移除全域 (Bot 擁有者)
        elif action == "remove_global":
            if not is_user_trusted(interaction.user.id):
                await interaction.response.send_message("❌ 此操作僅限 Bot 擁有者使用。", ephemeral=True)
                return

            success = remove_custom_bad_word("GLOBAL", word)
            if success:
                embed = discord.Embed(
                    title="🗑️ 全域敏感詞移除成功",
                    description=f"詞彙 `{word}` 已從全域詞庫移除，即時生效。",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.utcnow()
                )
                print(f"🌐 [BadWord] 移除全域詞彙: '{word}' by {interaction.user}")
            else:
                embed = discord.Embed(
                    title="❌ 詞彙不存在",
                    description=f"詞彙 `{word}` 不在全域詞庫中。",
                    color=discord.Color.red()
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="正則", description="[管理員/信任者] 管理 DB 正則規則，修改即時生效")
    @app_commands.describe(
        操作="新增、移除、列表或全域管理",
        規則="原始正則表達式，不需加 Python 的 r 前綴或外層引號；移除時需完全相同"
    )
    @app_commands.choices(操作=[
        app_commands.Choice(name="➕ 新增 (本伺服器)", value="add"),
        app_commands.Choice(name="➖ 移除 (本伺服器)", value="remove"),
        app_commands.Choice(name="📋 列表 (全域及本伺服器)", value="list"),
        app_commands.Choice(name="🌐 新增全域 (信任者 / 擁有者)", value="add_global"),
        app_commands.Choice(name="🗑️ 移除全域 (信任者 / 擁有者)", value="remove_global"),
    ])
    async def regex_command(
        self, interaction: discord.Interaction,
        操作: app_commands.Choice[str], 規則: str = None
    ):
        if not is_server_authorized(interaction.guild_id):
            await interaction.response.send_message("❌ 此伺服器尚未獲得機器人授權。", ephemeral=True)
            return
        is_admin = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        is_trusted = is_user_trusted(interaction.user.id)
        if not (is_admin or is_trusted):
            await interaction.response.send_message("❌ 需要伺服器管理員或機器人信任者權限。", ephemeral=True)
            return
        action = 操作.value
        if action.endswith("_global") and not is_trusted:
            await interaction.response.send_message("❌ 全域操作僅限機器人信任者或擁有者。", ephemeral=True)
            return

        try:
            if action == "list":
                entries = list_custom_regex_patterns_detail(str(interaction.guild_id))
                if not entries:
                    await interaction.response.send_message("📋 全域及本伺服器皆無正則規則。", ephemeral=True)
                    return
                # 跳脫 Markdown 以顯示原始規則；分頁避免超過 Discord 限制。
                pages, page = [], ""
                for entry in entries:
                    line = f"【{entry['scope']}】{discord.utils.escape_markdown(entry['pattern'])} — 由 {discord.utils.escape_markdown(entry['added_by'])}\n"
                    while line:
                        chunk, line = line[:3500], line[3500:]
                        if len(page) + len(chunk) > 3500:
                            pages.append(page)
                            page = ""
                        page += chunk
                if page:
                    pages.append(page)
                for index, description in enumerate(pages):
                    embed = discord.Embed(
                        title=f"📋 正則規則（{len(entries)} 筆）— {index + 1}/{len(pages)}",
                        description=description, color=discord.Color.blurple()
                    )
                    embed.set_footer(text="輸入原始正則，不含 Python r 前綴或外層引號；移除全域需信任者權限")
                    send = interaction.response.send_message if index == 0 else interaction.followup.send
                    await send(embed=embed, ephemeral=True)
                return

            if 規則 is None or not 規則 or len(規則) > 1000:
                await interaction.response.send_message("❌ 請填寫 1–1000 字元的原始正則規則。", ephemeral=True)
                return
            scope = "GLOBAL" if action.endswith("_global") else str(interaction.guild_id)
            scope_label = "全域" if scope == "GLOBAL" else "本伺服器"
            if action in ("add", "add_global"):
                success = add_custom_regex_pattern(
                    scope, 規則, f"{interaction.user.display_name} ({interaction.user.id})"
                )
                result = "新增成功，即時生效" if success else "已存在"
            elif action in ("remove", "remove_global"):
                success = remove_custom_regex_pattern(scope, 規則)
                result = "移除成功，即時生效" if success else "不存在（請確認範圍及原始規則完全相同）"
            else:
                await interaction.response.send_message("❌ 不支援的操作。", ephemeral=True)
                return
            await interaction.response.send_message(f"{scope_label}正則規則：{result}。", ephemeral=True)
        except (re.error, ValueError) as exc:
            await interaction.response.send_message(f"❌ 正則規則無效：{exc}", ephemeral=True)
        except sqlite3.Error:
            await interaction.response.send_message("❌ 資料庫操作失敗，請查看機器人日誌。", ephemeral=True)
            raise


async def setup(bot: commands.Bot):
    await bot.add_cog(BadWordCog(bot))
