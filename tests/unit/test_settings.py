import os

from config.settings import load_env_file


def test_load_env_file_sets_values_from_dotenv(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "TEST_KEY=value-one\nTELEGRAM_MESSAGE_HEADER=hello world\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("TEST_KEY", raising=False)
    monkeypatch.delenv("TELEGRAM_MESSAGE_HEADER", raising=False)

    load_env_file(str(env_path))

    assert os.environ["TEST_KEY"] == "value-one"
    assert os.environ["TELEGRAM_MESSAGE_HEADER"] == "hello world"
