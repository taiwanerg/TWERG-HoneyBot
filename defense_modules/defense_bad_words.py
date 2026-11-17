import datetime
import re
import discord

# 自訂表情的名稱、snowflake ID 都不是使用者輸入的文字。
CUSTOM_EMOJI_PATTERN = re.compile(r'<a?:[a-zA-Z0-9_]+:[0-9]+>')
UNICODE_EMOJI_PATTERN = re.compile(
    r'[0-9#*]\ufe0f?\u20e3'  # 鍵帽表情：整組排除，避免留下數字
    r'|[\U0001f000-\U0001faff\u2600-\u27bf'
    r'\u2300-\u23ff\u2b05-\u2b07\u2b1b\u2b1c\u2b50\u2b55'
    r'\u2194-\u2199\u21a9\u21aa\u2934\u2935'
    r'\u00a9\u00ae\u203c\u2049\u2122\u2139\u24c2'
    r'\u3030\u303d\u3297\u3299\ufe0e\ufe0f\u200d'
    r'\U000e0020-\U000e007f]'
)

def text_without_emojis(text: str) -> str:
    """僅供敏感詞比對使用；以空白隔開表情前後文字，避免拼出新詞。"""
    return UNICODE_EMOJI_PATTERN.sub(' ', CUSTOM_EMOJI_PATTERN.sub(' ', text))

def normalize_text(text: str) -> str:
    """歸一化文字：全角轉半角、大寫轉小寫、繁體轉簡體並剔除雜訊"""
    if not text:
        return ""
    # 全角轉半角
    res = []
    for char in text:
        code = ord(char)
        if code == 12288: # 全角空格
            res.append(' ')
        elif 65281 <= code <= 65374: # 全角英數標點
            res.append(chr(code - 65248))
        else:
            res.append(char)
    s = "".join(res).lower()
    
    # 簡易繁簡轉換表 (常見關鍵字)
    t2s = {
        '幹': '干', '驚': '惊', '爆': '爆', '炸': '炸', '彈': '弹',
        '殺': '杀', '死': '死', '爛': '烂', '賤': '贱', '雞': '鸡'
    }
    for t_char, s_char in t2s.items():
        s = s.replace(t_char, s_char)
    return s

async def check_bad_words(cog, message: discord.Message) -> bool:
    """
    敏感詞彙與組合正則特徵比對。
    比對範圍：DB 全域及伺服器敏感詞與正則規則。
    匹配成功時刪除訊息並執行 3 天禁言處決。
    回傳 True 表示已有處置，跳過後續檢查。
    """
    from settings.settings_utils import get_custom_bad_words, get_custom_regex_patterns

    raw_content = message.content or ""
    match_content = text_without_emojis(raw_content)
    norm_content = normalize_text(match_content)

    # 預設詞僅於首次初始化匯入 DB，刪除後不再從程式碼補回。
    all_words = get_custom_bad_words(str(message.guild.id))

    # 1. 關鍵字比對 (all_words)
    matched_word = None
    for bw in all_words:
        if bw in match_content or bw in norm_content:
            matched_word = bw
            break

    # 2. 組合式正則比對：僅使用 DB 規則。
    matched_regex = None
    if not matched_word:
        for pattern in get_custom_regex_patterns(str(message.guild.id)):
            try:
                matched = re.search(pattern, match_content) or re.search(pattern, norm_content)
            except re.error as exc:
                print(f"⚠️ [敏感詞模組] 跳過無效 DB 正則 {pattern!r}: {exc}")
                continue
            if matched:
                matched_regex = pattern
                break

    if matched_word or matched_regex:
        try:
            await message.delete()
        except Exception:
            pass
        bot_member = message.guild.get_member(cog.bot.user.id) or await message.guild.fetch_member(cog.bot.user.id)
        if bot_member.guild_permissions.moderate_members and bot_member.top_role > message.author.top_role:
            try:
                reason = f"匹配至違規敏感詞彙或特徵正則 ({matched_word or '組合正則特徵'})"
                await message.author.timeout(datetime.timedelta(days=3), reason=reason)
                await cog._send_kill_announcement(message.channel, message.author, f"發言匹配至違規敏感詞/正則 ({matched_word or '正則特徵'})", raw_content=raw_content)
                print(f"🚨 [敏感詞模組] 已禁言 3 天違規用戶 {message.author} ({message.author.id}) - 匹配詞: {matched_word or matched_regex}")
            except Exception as e:
                print(f"⚠️ [敏感詞模組] 處決違規用戶失敗: {e}")
        return True
    return False

