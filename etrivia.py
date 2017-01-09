import discord
import math
from discord.ext import commands
from random import choice as randchoice
from .utils.dataIO import dataIO
from .utils import checks
import time
import os
import asyncio
import chardet
import sqlite3
import glob
import random
import operator


class ETrivia(object):
    """General commands."""

    def __init__(self, bot):
        self.bot = bot
        self.etrivia_sessions = []
        self.themes = {}
        self.questions = {}

        self.file_path = "data/etrivia/settings.json"
        self.settings = dataIO.load_json(self.file_path)
        self.dbc = sqlite3.connect("ETrivia.db")
        self._prepare_db()
        # self.import_files()
        self._fill_cache()
        self.dbc.commit()

    def _prepare_db(self):
        self.dbc.execute('''
        CREATE TABLE IF NOT EXISTS theme(
            `id` INTEGER PRIMARY KEY AUTOINCREMENT,
            `name` VARCHAR(255) UNIQUE
        );
        ''')
        self.dbc.execute('''
        CREATE TABLE IF NOT EXISTS question(
            `id` INTEGER PRIMARY KEY AUTOINCREMENT,
            `theme_id` INTEGER,
            `text` TEXT NOT NULL,
            `answer` TEXT NOT NULL,
            `asked` BOOLEAN,
            FOREIGN KEY(`theme_id`) REFERENCES `theme`(`id`)
        );
        ''')
        self.dbc.execute('''
        CREATE TABLE IF NOT EXISTS rating (
            `server_id` VARCHAR(255) NOT NULL,
            `user_id` VARCHAR(255) NOT NULL,
            `username` VARCHAR(255),
            `total_games` INT(11)  DEFAULT 0,
            `wins` INT(11) DEFAULT 0,
            `right_answers` INT(11) DEFAULT 0,
            PRIMARY KEY(`server_id`, `user_id`)
        );
        ''')
        pass

    def _fill_cache(self, theme=None):
        c = self.dbc.cursor()
        q = "SELECT * FROM `theme`"
        d = tuple()
        if theme:
            q += " WHERE id=?"
            d = (theme[0], )
        else:
            self.questions.clear()
        c.execute(q, d)
        for theme in c.fetchall():
            c.execute("SELECT id FROM question WHERE theme_id = ?", (theme[0],))
            if theme[1] in self.questions:
                self.questions[theme[1]].clear()
            self.questions[theme[1]] = [v[0] for v in c.fetchall()]
            random.shuffle(self.questions[theme[1]])
            if not self.questions[theme[1]]:
                del self.questions[theme[1]]

    def guess_encoding(self, trivia_list):
        with open(trivia_list, "rb") as f:
            try:
                return chardet.detect(f.read())["encoding"]
            except:
                return "ISO-8859-1"

    def get_theme(self, theme):
        c = self.dbc.cursor()
        c.execute("SELECT * FROM theme WHERE name = ?", (theme,))
        t = c.fetchone()
        c.close()
        return t

    def flush_questions(self, theme_id: int):
        self.dbc.execute("DELETE FROM question WHERE theme_id = ?", (theme_id,))

    def get_top(self, server_id: int, limit: int, order: str):
        """
        :param server_id:
        :param limit:
        :param order: Order criteria, available are `wise`, `games`, `victory`
        :return:
        """
        c = self.dbc.cursor()
        query = "SELECT * FROM rating %s ORDER BY "
        if order == "games":
            query += " total_games"
        elif order == "victory":
            query += " wins"
        else:
            query += " right_answers"
        data = tuple()
        if server_id:
            data = (server_id,)
            query %= "WHERE server_id = ?"
        else:
            query %= ""
        query += " DESC"
        c.execute(query, data)
        return [{"username": i[2], "games": i[3], "wins": i[4], "answers": i[5]} for i in c.fetchall()]

    def get_themes(self, loaded: bool = True):
        if loaded:
            return self.questions.keys()
        files = glob.glob("data/etrivia/*.txt")
        return [f[f.rfind(os.sep)+1:-4] for f in files]

    def create_theme_if_not_exists(self, theme: str):
        """
        Create theme if not exists
        :param theme:
        :return:
        """
        db_theme = self.get_theme(theme)
        is_new = False
        if db_theme is None:
            self.dbc.execute("INSERT INTO theme (name) VALUES(?)", (theme,))
            db_theme = self.get_theme(theme)
            is_new = True
        return is_new, db_theme

    async def load_file(self, theme: str, force: bool):
        success = False
        try:
            if theme is None or theme is "":
                await self.bot.say("File name is required")
                return False

            is_new, theme = self.create_theme_if_not_exists(theme)

            if theme is None:
                await self.bot.say("Произошла ошибка. Тема под названием `{}` не была создана".format(theme[1]))

            if not is_new:
                if not force:
                    await self.bot.say("Тема уже была импортирована")
                    return False
                self.flush_questions(theme[0])
                theme = theme

            filename = "data/etrivia/" + theme[1] + ".txt"

            if os.path.isfile(filename):
                self.import_file(filename, theme[0])
                success = True
                await self.bot.say("Тема под названием `{}` успешно импортирована из файла".format(theme[1]))
                return True
            else:
                await self.bot.say("File {} not found".format(filename))
                return False
        finally:
            if not success:
                self.dbc.rollback()
            else:
                self.dbc.commit()

    def import_file(self, file_name: str, theme_id: int):
        encoding = self.guess_encoding(file_name)
        with open(file_name, "r", encoding=encoding) as fin:
            for line in fin:
                if "`" in line and len(line) > 4:
                    line = line.replace("\n", "")
                    line = line.split("`")
                    question = line[0]
                    answer = line[1]
                    if len(line) >= 2:
                        self.dbc.execute("INSERT INTO question(`theme_id`, `text`, `answer`) VALUES(?, ?, ?)",
                                         (theme_id, question, answer))

    @commands.group(pass_context=True)
    async def etrivia(self, ctx):
        if ctx.invoked_subcommand is None:
            msg = "```\n"
            msg += "```\n"

    @etrivia.command()
    @checks.mod_or_permissions(administrator=True)
    async def load(self, theme: str, force: bool = False):
        """
        Loading questions from file
        :param theme: Theme's file's name
        :param force: ignore theme's existence
        :return:
        """
        await self.bot.say("I'm starting to load theme {}".format(theme))
        await self.load_file(theme, force)
        self._fill_cache(theme)
        await self.bot.say("Theme {} was loaded successfully!".format(theme))

    @etrivia.command()
    @checks.mod_or_permissions(administrator=True)
    async def loadall(self, force: bool = False):
        """
        Loading all available themes
        :param force: ignore themes' existence
        :return:
        """
        themes = self.get_themes(False)
        await self.bot.say("I'm starting to load {} themes".format(len(themes)))
        for idx, theme in enumerate(themes):
            await self.bot.say("{}. I'm starting to load theme {}".format(idx, theme))
            if await self.load_file(theme, force):
                await self.bot.say("Theme {} was loaded successfully".format(theme))
        self._fill_cache()
        await self.bot.say("All themes was loaded")

    @commands.group(pass_context=True)
    @checks.mod_or_permissions(administrator=True)
    async def etriviaset(self, ctx):
        """Change etrivia settings"""
        if ctx.invoked_subcommand is None:
            msg = "```\n"
            for k, v in self.settings.items():
                msg += "{}: {}\n".format(k, v)
            msg += "```\nSee {}help etriviaset to edit the settings".format(ctx.prefix)
            await self.bot.say(msg)

    @etriviaset.command()
    async def maxscore(self, score: int):
        """Points required to win"""
        if score > 0:
            self.settings["ETRIVIA_MAX_SCORE"] = score
            dataIO.save_json(self.file_path, self.settings)
            await self.bot.say("Points required to win set to {}".format(str(score)))
        else:
            await self.bot.say("Score must be superior to 0.")

    @etriviaset.command()
    async def timelimit(self, seconds: int):
        """Maximum seconds to answer"""
        if seconds > 4:
            self.settings["ETRIVIA_DELAY"] = seconds
            dataIO.save_json(self.file_path, self.settings)
            await self.bot.say("Maximum seconds to answer set to {}".format(str(seconds)))
        else:
            await self.bot.say("Seconds must be at least 5.")

    @etriviaset.command()
    async def botplays(self):
        """Red gains points"""
        if self.settings["ETRIVIA_BOT_PLAYS"] is True:
            self.settings["ETRIVIA_BOT_PLAYS"] = False
            await self.bot.say("Alright, I won't embarass you at etrivia anymore.")
        else:
            self.settings["ETRIVIA_BOT_PLAYS"] = True
            await self.bot.say("I'll gain a point everytime you don't answer in time.")
        dataIO.save_json(self.file_path, self.settings)

    @etrivia.command(pass_context=True)
    async def top(self, ctx, order_by: str = "wise", limit: int = 10):
        """
        Top of the best ETrivia players
        order_by - sorting order. Available are "wise", "games", "victory"
        limit - limit
        """
        top = self.get_top(ctx.message.server.id, limit, order_by)
        msg = "**Рейтинг игроков:** \n```\n{0:3}\t{1:10}\t{2:5}\t{3:5}\t{4:5}\n".format("#", "Имя", "Игры", "Победы",
                                                                                        "Ответы")
        for idx, player in enumerate(top):
            line = "{0:3}\t{1:10}\t{2:5}\t{3:5}\t{4:5}\n".format(idx + 1, player["username"], player["games"],
                                                                 player["wins"],
                                                                 player["answers"])
            if len(msg) + len(line) > 2000:
                msg += "````"
                await self.bot.say(msg)
                msg = "```"
            msg += line
        msg += "```"
        await self.bot.say(msg)

    @etrivia.command(pass_context=True)
    async def start(self, ctx, theme: str = None):
        """Start an etrivia session with the specified theme
        """
        message = ctx.message
        if not await get_trivia_by_channel(message.channel):
            if theme in self.questions:
                t = TriviaSession(message, self.settings, self.questions[theme], self.dbc)
                self.etrivia_sessions.append(t)
                await t.in_game()
        else:
            await self.bot.say("A Etrivia session is already ongoing in this channel.")

    @etrivia.command(pass_context=True)
    async def stop(self, ctx):
        """
        Stop the etrivia session in the channel
        :param ctx:
        :return:
        """
        message = ctx.message
        if await get_trivia_by_channel(message.channel):
            s = await get_trivia_by_channel(message.channel)
            await s.end_game()
            await self.bot.say("Etrivia stopped.")
        else:
            await self.bot.say("There's no Etrivia session ongoing in this channel.")

    @etrivia.command(pass_context=True)
    async def list(self, ctx):
        """
        List of all available themes
        """
        await self.trivia_list(ctx.message.author)

    async def trivia_list(self, author):
        msg = "**Available Etrivia lists:** \n\n```"
        if self.questions:
            i = 0
            for theme in self.questions.keys():
                if i % 4 == 0 and i != 0:
                    msg += theme + "\n"
                else:
                    msg += theme + "\t"
                i += 1
            msg += "```"
            if len(self.themes) > 100:
                await self.bot.send_message(author, msg)
            else:
                await self.bot.say(msg)
        else:
            await self.bot.say("There are no etrivia lists available.")


class TriviaSession(object):
    def __init__(self, message, settings, question_list, dbc):
        self.gave_answer = ["I know this one! {}!", "Easy: {}.", "Oh really? It's {} of course."]
        self.current_q = None  # {"QUESTION" : "String", "ANSWER" : ""}
        self.masked_answer = ""
        self.hints_count = 0
        self.question_list = ""
        self.channel = message.channel
        self.score_list = {}
        self.status = None
        self.timer = None
        self.count = 0
        self.settings = settings
        self.question_list = question_list
        self.dbc = dbc
        self.server_id = message.server.id

    def get_question(self, q_id: int):
        c = self.dbc.cursor()
        c.execute("SELECT * FROM question WHERE id=?", (q_id,))
        q = c.fetchone()
        return {
            'text': q[2],
            'answer': q[3]
        }

    def save_or_update_user(self, server_id: int, user, plus_games: int = 0, plus_answers: int = 0,
                            plus_wins: int = 0):
        self.dbc.execute("""
        INSERT OR IGNORE INTO `rating` (server_id, user_id, username)
        VALUES (
            ?, ?, ?
        )
        """, (server_id, user.id, user.name))
        self.dbc.execute("""
        UPDATE `rating` SET total_games = total_games + ?, wins = wins + ?, right_answers = right_answers + ?
        WHERE server_id=? AND user_id=?
        """, (plus_games, plus_wins, plus_answers, server_id, user.id))
        self.dbc.commit()

    async def in_game(self):
        await self.new_question()

    async def stop_etrivia(self):
        self.status = "stop"
        etrivia_manager.etrivia_sessions.remove(self)

    async def end_game(self):
        self.status = "stop"
        if self.score_list:
            best_player = max(self.score_list.items(), key=operator.itemgetter(1))[0]
            self.save_or_update_user(self.server_id, best_player, 0, 0, 1)
            await self.send_table()
        etrivia_manager.etrivia_sessions.remove(self)

    async def new_question(self):
        for score in self.score_list.values():
            if score == self.settings["ETRIVIA_MAX_SCORE"]:
                await self.end_game()
                return True
        if not self.question_list:
            await self.end_game()
            return True
        q = self.question_list.pop()
        while q is None and self.question_list:
            q = self.question_list.pop()

        self.current_q = self.get_question(q)
        self.masked_answer = ""
        self.hints_count = 0
        for c in self.current_q["answer"]:
            if c == ' ' or c == '-' or c == '(' or c == ')':
                self.masked_answer += c
            else:
                self.masked_answer += '*'

        self.status = "waiting for answer"
        self.count += 1
        self.timer = int(time.perf_counter())
        msg = "**Вопрос №{}!**\n\n{} Букв: {}.".format(str(self.count), self.current_q["text"],
                                                       self.get_answer_length())
        try:
            await etrivia_manager.bot.say(msg)
        except:
            await asyncio.sleep(0.5)
            await etrivia_manager.bot.say(msg)

        while self.status == "waiting for answer":
            if abs(self.timer - int(time.perf_counter())) >= self.settings["ETRIVIA_DELAY"]:
                if self.masked_answer.count('*') > 2:
                    self.timer = int(time.perf_counter())
                    await self.show_hint()
                else:
                    self.status = "no answer"
                    break
            else:
                if abs(self.timeout - int(time.perf_counter())) >= self.settings["ETRIVIA_TIMEOUT"]:
                    await etrivia_manager.bot.say("Guys...? Well, I guess I'll stop then.")
                    await self.stop_etrivia()
                    return True
            await asyncio.sleep(1)  # Waiting for an answer or for the time limit
        if self.status == "correct answer":
            self.status = "new question"
            await asyncio.sleep(3)
            if not self.status == "stop":
                await self.new_question()
        elif self.status == "stop":
            return True
        else:
            msg = randchoice(self.gave_answer).format(self.current_q["answer"])
            if self.settings["ETRIVIA_BOT_PLAYS"]:
                msg += " **+1** for me!"
                self.add_point(etrivia_manager.bot.user.name)
            self.current_q["answer"] = ""
            try:
                await etrivia_manager.bot.say(msg)
                await etrivia_manager.bot.send_typing(self.channel)
            except:
                await asyncio.sleep(0.5)
                await etrivia_manager.bot.say(msg)
            await asyncio.sleep(3)
            if not self.status == "stop":
                await self.new_question()

    async def send_table(self):
        self.score_list = sorted(self.score_list.items(), reverse=True,
                                 key=lambda x: x[1])  # orders score from lower to higher
        t = "```Scores: \n\n"
        for score in self.score_list:
            t += "@" + score[0].name  # name
            t += "\t"
            t += str(score[1])  # score
            t += "\n"
        t += "```"
        await etrivia_manager.bot.say(t)

    async def check_answer(self, message: discord.message.Message):
        if message.author.id != etrivia_manager.bot.user.id:
            self.timeout = time.perf_counter()
            if self.current_q is not None and self.current_q["answer"] != "":
                if self.current_q["answer"].lower() in message.content.lower():
                    self.current_q["answer"] = ""
                    self.status = "correct answer"
                    self.add_point(message)
                    msg = "You got it {}! **+1** to you!".format(message.author.name)
                    try:
                        await etrivia_manager.bot.send_typing(self.channel)
                        await etrivia_manager.bot.send_message(message.channel, msg)
                    except:
                        await asyncio.sleep(0.5)
                        await etrivia_manager.bot.send_message(message.channel, msg)
                    return True

    async def show_hint(self):
        letters_count = 0
        self.hints_count += 1
        number_sequence = []
        for i, c in enumerate(self.masked_answer):
            if c == '*':
                number_sequence.append(i)
                letters_count += 1

        for x in range(0, math.ceil(letters_count / 5.0)):
            i = randchoice(number_sequence)
            number_sequence.remove(i)
            letter_to_show = self.current_q["answer"][i]
            self.masked_answer = self.masked_answer[:i] + letter_to_show + self.masked_answer[i + 1:]

        msg = "**Подсказка №{}!** `{}`".format(self.hints_count, self.masked_answer)

        try:
            await etrivia_manager.bot.say(msg)
            await etrivia_manager.bot.send_typing(self.channel)
        except:
            await asyncio.sleep(0.5)
            await etrivia_manager.bot.say(msg)

    def get_answer_length(self):
        if self.current_q is not None:
            return len(self.current_q["answer"])

    def add_point(self, message: discord.message.Message):
        if message.author in self.score_list:
            self.score_list[message.author] += 1
            self.save_or_update_user(message.server.id, message.author, 0, 1)
        else:
            self.score_list[message.author] = 1
            self.save_or_update_user(message.server.id, message.author, 1, 1)


async def get_trivia_by_channel(channel):
    for t in etrivia_manager.etrivia_sessions:
        if t.channel == channel:
            return t
    return False


async def check_messages(message):
    if message.author.id != etrivia_manager.bot.user.id:
        if await get_trivia_by_channel(message.channel):
            trvsession = await get_trivia_by_channel(message.channel)
            await trvsession.check_answer(message)


def check_folders():
    folders = ("data", "data/etrivia/")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)


def check_files():
    settings = {"ETRIVIA_MAX_SCORE": 10, "ETRIVIA_TIMEOUT": 120, "ETRIVIA_DELAY": 10, "ETRIVIA_BOT_PLAYS": False}

    if not os.path.isfile("data/etrivia/settings.json"):
        print("Creating empty settings.json...")
        dataIO.save_json("data/etrivia/settings.json", settings)


def setup(bot):
    global etrivia_manager
    check_folders()
    check_files()
    bot.add_listener(check_messages, "on_message")
    etrivia_manager = ETrivia(bot)
    bot.add_cog(etrivia_manager)
