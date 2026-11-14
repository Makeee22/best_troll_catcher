import csv
import zipfile
from swarm.cresci import convert


def make_set(folder, name, users, tweets):
    def text(rows):
        return "\n".join(",".join(f'"{v}"' for v in row) for row in rows) + "\n"
    with zipfile.ZipFile(folder / f"{name}.csv.zip", "w") as z:
        z.writestr(f"{name}.csv/users.csv", text(users))
        z.writestr(f"{name}.csv/tweets.csv", text(tweets))


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_convert(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir(); out.mkdir()
    users = [["id", "name", "screen_name", "followers_count", "friends_count", "statuses_count", "default_profile_image", "verified", "timestamp"],
             ["11", "Real Name", "realhandle", "5", "7", "2", "NULL", "NULL", "2012-01-05 08:00:00"]]
    tweets = [["id", "text", "source", "user_id", "in_reply_to_status_id", "retweeted_status_id", "favorite_count", "timestamp"],
              ["900", "hello world", '<a href=x rel=nofollow>web</a>', "11", "0", "0", "3", "2014-03-01 10:00:00"],
              ["901", "RT something", "web", "11", "NULL", "555", "0", "2014-03-01 10:05:00"],
              ["902", "no time", "web", "11", "0", "0", "0", ""]]
    make_set(src, "genuine_accounts", users, tweets)
    make_set(src, "social_spambots_1", [users[0], ["22", "Bot", "bothandle", "0", "0", "1", "1", "NULL", "2012-01-06 08:00:00"]],
             [tweets[0], ["903", "buy now", "web", "22", "900", "0", "0", "2014-03-02 10:00:00"]])
    convert(str(src), str(out))

    comments, profiles = read(out / "comments.csv"), read(out / "profiles.csv")
    assert [(c["comment_id"], c["username"], c["timestamp"], c["parent_id"], c["repost_of"], c["client"]) for c in comments] == [
        ("900", "11", "2014-03-01T10:00:00Z", "", "", "web"),
        ("901", "11", "2014-03-01T10:05:00Z", "", "555", "web"),
        ("903", "22", "2014-03-02T10:00:00Z", "900", "", "web")]
    assert [(p["username"], p["label"], p["created_at"], p["default_avatar"]) for p in profiles] == [
        ("11", "human", "2012-01-05T08:00:00Z", "0"), ("22", "bot:social_1", "2012-01-06T08:00:00Z", "1")]
    everything = (out / "comments.csv").read_text() + (out / "profiles.csv").read_text()
    assert "Real Name" not in everything and "realhandle" not in everything and "bothandle" not in everything


def test_fake_followers_layout_and_odd_values(tmp_path, capsys):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir(); out.mkdir()
    # no users.timestamp: created_at is Twitter's format; a profile without tweets, a tweet without a profile
    users = [["id", "name", "screen_name", "created_at"],
             ["31", "N", "S", "Thu Apr 06 15:24:15 +0000 2007"],
             ["32", "N", "S", "NULL"],
             ["0", "N", "S", "NULL"]]
    tweets = [["created_at", "id", "text", "source", "user_id", "timestamp"],
              ["x", "1", "a\x00b", "web", "31", "2014-03-01 10:00:00"],
              ["x", "2", "orphan", "web", "99", "2014-03-01 10:00:00"],
              ["x", "3", "no user", "web", "\\N", "2014-03-01 10:00:00"],
              ["x", "4", "bad time", "web", "31", "garbage"]]
    make_set(src, "fake_followers", users, tweets)
    convert(str(src), str(out))

    comments, profiles = read(out / "comments.csv"), read(out / "profiles.csv")
    assert [(c["comment_id"], c["username"], c["text"]) for c in comments] == [("1", "31", "ab"), ("2", "99", "orphan")]
    assert [(p["username"], p["label"], p["created_at"]) for p in profiles] == [
        ("31", "bot:fake_followers", "2007-04-06T15:24:15Z"), ("32", "bot:fake_followers", "")]
    assert "genuine_accounts" in capsys.readouterr().out
