"""The following code is (c) sliceofcode 2017."""
"""Source: https://github.com/sliceofcode/dogbot/blob/master/dog/core/ext/exec.py """

"""
Handy exec (eval, debug) cog. Allows you to run code on the bot during runtime. This cog
is a combination of the exec commands of other bot authors:

Credit:
    - Rapptz (Danny)
        - https://github.com/Rapptz/RoboDanny/blob/master/cogs/repl.py#L31-L75
    - b1naryth1ef (B1nzy, Andrei)
        - https://github.com/b1naryth1ef/b1nb0t/blob/master/plugins/util.py#L220-L257

Features:
    - Strips code markup (code blocks, inline code markup)
    - Access to last result with _
    - _get and _find instantly available without having to import discord
    - Redirects stdout so you can print()
    - Sane syntax error reporting
"""

import io
import logging
import textwrap
import traceback
from contextlib import redirect_stdout

import aiohttp
import discord
from discord.ext import commands

from cogs.utils import paste

log = logging.getLogger(__name__)


def strip_code_markup(content: str) -> str:
    """ Strips code markup from a string. """
    # ```py
    # code
    # ```
    if content.startswith('```') and content.endswith('```'):
        # grab the lines in the middle
        return '\n'.join(content.split('\n')[1:-1])

    # `code`
    return content.strip('` \n')


def format_syntax_error(e: SyntaxError) -> str:
    """ Formats a SyntaxError. """
    if e.text is None:
        return '```py\n{0.__class__.__name__}: {0}\n```'.format(e)
    # display a nice arrow
    return '```py\n{0.text}{1:>{0.offset}}\n{2}: {0}```'.format(e, '^', type(e).__name__)


class Exec:
    def __init__(self, bot, *args, **kwargs):
        self.bot = bot
        self.last_result = None

    @commands.command(name='eval', aliases=['exec', 'debug'])
    @commands.is_owner()
    async def _eval(self, ctx, *, code: str):
        """ Executes Python code. """
        async def upload(file_name: str):
            with open(file_name, 'rb') as fp:
                await ctx.send(file=discord.File(fp))

        async def send(*args, **kwargs):
            await ctx.send(*args, **kwargs)

        env = {
            'self': self,
            'bot': ctx.bot,
            'ctx': ctx,
            'msg': ctx.message,
            'guild': ctx.guild,
            'channel': ctx.channel,
            'me': ctx.message.author,

            # utilities
            '_get': discord.utils.get,
            '_find': discord.utils.find,
            '_upload': upload,
            '_send': send,

            # last result
            '_': self.last_result
        }

        env.update(globals())

        # remove any markup that might be in the message
        code = strip_code_markup(code)

        # add an implicit return at the end
        lines = code.split('\n')
        if not lines[-1].startswith('return') and not lines[-1].startswith(' '):
            lines[-1] = 'return ' + lines[-1]
        code = '\n'.join(lines)

        # simulated stdout
        stdout = io.StringIO()

        # wrap the code in a function, so that we can use await
        wrapped_code = 'async def func():\n' + textwrap.indent(code, '    ')

        try:
            exec(compile(wrapped_code, '<exec>', 'exec'), env)
        except SyntaxError as e:
            return await ctx.send(format_syntax_error(e))

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            # something went wrong
            stream = stdout.getvalue()
            await ctx.send('```py\n{}{}\n```'.format(stream, traceback.format_exc()))
        else:
            # successful
            stream = stdout.getvalue()

            try:
                await ctx.message.add_reaction('\u2705')
            except:
                # couldn't add the reaction, ignore
                log.warning('Failed to add reaction to eval message, ignoring.')

            try:
                self.last_result = self.last_result if ret is None else ret
                await ctx.send('```py\n{}{}\n```'.format(stream, repr(ret)))
            except discord.HTTPException:
                # too long
                try:
                    url = await paste(ctx.bot.session, stream + repr(ret))
                    await ctx.send('Result was too long. ' + url)
                except KeyError:
                    # even hastebin couldn't handle it
                    await ctx.send('Result was too long, even for Hastebin.')
                except aiohttp.ClientError:
                    await ctx.send('Unable to send the result to Hastebin, it\'s probably down.')


def setup(bot):
    bot.add_cog(Exec(bot))
