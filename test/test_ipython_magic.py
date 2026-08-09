import asyncio
import signal
import textwrap
from threading import Thread
from time import sleep

import pytest

from test.fake_time_util import fake_time

from .util import strip_ansi

# note: IPython should be imported within each test. Importing it in our tests
# seems to cause problems with subsequent tests.

cell_code = """
import time

def function_a():
    function_b()
    function_c()

def function_b():
    function_d()

def function_c():
    function_d()

def function_d():
    function_e()

def function_e():
    time.sleep(0.1)

function_a()
"""

# Tests #


@pytest.mark.ipythonmagic
def test_magics(ip):
    from IPython.utils.capture import capture_output as capture_ipython_output

    with fake_time():
        with capture_ipython_output() as captured:
            ip.run_cell_magic("pyinstrument", line="", cell=cell_code)

    assert len(captured.outputs) == 1
    output = captured.outputs[0]
    assert "text/html" in output.data
    assert "text/plain" in output.data

    assert "function_a" in output.data["text/html"]
    assert "<iframe" in output.data["text/html"]
    plain_text = strip_ansi(output.data["text/plain"])
    assert "function_a" in plain_text

    assert "0.200 function_a" in plain_text
    assert "0.100 FakeClock.sleep" in plain_text

    with fake_time():
        with capture_ipython_output() as captured:
            # this works because function_a was defined in the previous cell
            ip.run_line_magic("pyinstrument", line="function_a()")

    assert len(captured.outputs) == 1
    output = captured.outputs[0]

    plain_text = strip_ansi(output.data["text/plain"])
    assert "function_a" in plain_text
    assert "0.100 FakeClock.sleep" in plain_text


@pytest.mark.ipythonmagic
def test_magic_empty_line(ip):
    # check empty line input
    ip.run_line_magic("pyinstrument", line="")


@pytest.mark.ipythonmagic
def test_magic_no_variable_expansion(ip, capsys):
    ip.run_line_magic("pyinstrument", line="print(\"hello {len('world')}\")")

    captured = capsys.readouterr()
    assert "hello {len('world')}" in captured.out
    assert "hello 5" not in captured.out


@pytest.mark.ipythonmagic
def test_pyinstrument_handles_interrupt_silently(ip, capsys):
    from pyinstrument.magic.magic import InterruptSilently

    thread = Thread(target=_interrupt_after_1s)
    thread.start()
    # expect our custom exception to bubble up
    with pytest.raises(InterruptSilently):
        ip.run_cell_magic("pyinstrument", "", "from time import sleep; sleep(2)")

    thread.join()
    # nothing should have hit stderr
    _, err = capsys.readouterr()
    assert err.strip() == ""


@pytest.mark.ipythonmagic
@pytest.mark.filterwarnings("error:.*run_cell_async.*transform_cell.*:DeprecationWarning")
def test_async_cell_with_pyinstrument(ip, capsys):
    ip.run_cell_magic(
        "pyinstrument",
        line="--async_mode=enabled",
        cell=textwrap.dedent(
            """
            import asyncio
            async def function_a():
                await asyncio.sleep(0.1)
                return 42
            a = await function_a()
            print("a:", a)
            """
        ),
    )
    stdout, stderr = capsys.readouterr()
    assert "a: 42" in stdout


@pytest.mark.ipythonmagic
def test_run_cell_async_cleans_up_event_loop(monkeypatch):
    from pyinstrument.magic.magic import PyinstrumentMagic

    class FakeIP:
        def transform_cell(self, code):
            return code

        async def run_cell_async(self, code, **kwargs):
            await asyncio.sleep(0)
            return code

    created_loops = []
    created_threads = []
    real_new_event_loop = asyncio.new_event_loop

    def new_event_loop():
        loop = real_new_event_loop()
        created_loops.append(loop)
        return loop

    def new_thread(*args, **kwargs):
        thread = Thread(*args, **kwargs)
        created_threads.append(thread)
        return thread

    monkeypatch.setattr("pyinstrument.magic.magic.asyncio.new_event_loop", new_event_loop)
    monkeypatch.setattr("pyinstrument.magic.magic.threading.Thread", new_thread)

    previous_loop = real_new_event_loop()
    asyncio.set_event_loop(previous_loop)
    try:
        result = PyinstrumentMagic(shell=None).run_cell_async(FakeIP(), "result")

        assert result == "result"
        assert asyncio.get_event_loop() is previous_loop
        assert len(created_loops) == 1
        assert created_loops[0].is_closed()
        assert len(created_threads) == 1
        assert not created_threads[0].is_alive()
    finally:
        asyncio.set_event_loop(None)
        previous_loop.close()


@pytest.mark.ipythonmagic
def test_run_cell_async_without_current_event_loop():
    from pyinstrument.magic.magic import PyinstrumentMagic

    class FakeIP:
        def transform_cell(self, code):
            return code

        async def run_cell_async(self, code, **kwargs):
            return code

    asyncio.set_event_loop(None)

    assert PyinstrumentMagic(shell=None).run_cell_async(FakeIP(), "result") == "result"
    with pytest.raises(RuntimeError, match="There is no current event loop"):
        asyncio.get_event_loop()


# Utils #


@pytest.fixture(scope="module")
def session_ip():
    from IPython.testing.globalipapp import start_ipython

    yield start_ipython()


def _interrupt_after_1s():
    sleep(1)
    signal.raise_signal(signal.SIGINT)


@pytest.fixture(scope="function")
def ip(session_ip):
    session_ip.run_line_magic(magic_name="load_ext", line="pyinstrument")
    yield session_ip
    session_ip.run_line_magic(magic_name="reset", line="-f")
