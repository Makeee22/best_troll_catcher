# Examples

Results produced **locally** with the core, ready for the website's example tab. They are in the standard result
format (`docs/api.md`), so the backend serves one as it is: `RESULT_FILE=examples/cresci-2017-anonymised/result.json
uvicorn swarm.api:app` (from `backend/`).

## `cresci-2017-anonymised/result.json`

The core run on the whole **Cresci 2017** dataset (Twitter, 2014: 6.6 million tweets; 9,076 bots in three social
spambot families plus traditional spambots, 1,083 genuine accounts), on `main` of 15.11.2026, default settings, rules only.

| Precision | Recall | False-positive rate | Clusters | Accounts in clusters |
|---|---|---|---|---|
| 0.9999 | 0.833 | 0.0009 (1 of 1,083 genuine accounts) | 16 | 8,767 |

The confidence cut (0.2) is the one value chosen with the labels visible. Labels measure, they never train.

**Anonymised, because Cresci 2017 is licensed for research use only and holds real people's tweets.** Nothing in
the file can be traced back to an account or a tweet:
- usernames are `account 1`, `account 2`, … (the same number everywhere in the file);
- every shared item is a placeholder such as `shared text #2 (12 words)` or `shared link #7`;
- cluster ids are `cluster-1`, …; times are rounded down to the hour; the input warnings are left out.

Kept as computed: cluster sizes, confidences, every member's copied share and flag, the links between members and
how much they share, copy gaps, creation-window counts, the signals, the diagnostics and the metrics per bot family.

Made with `examples/anonymise.py`, which refuses to write the file unless every string in it is one of the known
safe forms (placeholders, the core's own keys and sentences, hour times, labels) and none equals a username or
text of the source:

```bash
python -m swarm data/cresci-std/comments.csv --profiles data/cresci-std/profiles.csv --out /tmp/cresci.json   # from backend/
python examples/anonymise.py /tmp/cresci.json examples/cresci-2017-anonymised/result.json \
    --label "Cresci 2017 (research data, anonymised)" --check backend/data/cresci-std/comments.csv
```

Source: Cresci et al., "The paradigm-shift of social spambots", WWW 2017 (http://mib.projects.iit.cnr.it).

**For the example tab:** say that it is research data, anonymised, and that the evidence texts are placeholders;
show the metrics with the note that the cut was chosen with labels visible. As everywhere: a flag is a reason to
watch an account, not a verdict.
