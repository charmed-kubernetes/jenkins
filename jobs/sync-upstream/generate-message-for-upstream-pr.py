from datetime import datetime
import requests
import os
from subprocess import check_output

GITHUB_API = "https://api.github.com/"
GITHUB_API_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "Authorization": "token {}".format(os.environ['GITHUB_AUTH'])
}


# uses github api to get a list of PRs for a given repository
# returns a json list of prs
def get_pr_list(owner="juju-solutions", repo="kubernetes"):
    url = "{}repos/{}/{}/pulls?state=closed".format(GITHUB_API, owner, repo)
    response = requests.get(url, headers=GITHUB_API_HEADERS)
    return [r for r in response.json() if r['merged_at'] != '']


# uses git log to get a list of commits that are in the from_branch that do
# not exist in the to_branch. basically, what will I merge over to to_branch
# when I merge. Note the time lag between this log call and the actual
# merge might miss things. I don't know a good way around that yet.
def get_commit_list_to_merge(to_branch="staging", from_branch="master"):
    to_run = ['git', 'log', "--format=%H %ct", '{}..{}'.format(
        to_branch, from_branch)]
    commit_spew = check_output(to_run).decode('utf-8')
    commits = [(l.split()[0], datetime.fromtimestamp(float(l.split()[1])))
               for l in commit_spew.splitlines()]
    return commits


# takes the json returned from the github api and
# returns a json list of commits from that PR
def get_commit_list_for_pr(pr_json):
    url = pr_json['commits_url']
    response = requests.get(url, headers=GITHUB_API_HEADERS)
    return response.json()


def pr_commit_in_commit_list(pr_json_sha, commit_list):
    for item in commit_list:
        if item[0] == pr_json_sha:
            return True
    return False


# pulls the release note out of a PR's json blob
def parse_pr_body_for_release_note(pr_json):
    parts = pr_json['body'].split('```')
    for part in parts:
        p = part.strip()
        if p.startswith('release-note'):
            note = p[12:].lstrip()
            if note.lower() == 'none':
                return None
            else:
                return note
    return None


# generates a file that can be used as a PR commit message
# from all the PR release notes with commits that show up
# in this PR
def write_pr_commit_message():
    commit_list = get_commit_list_to_merge()
    oldest_commit_timestamp = min(commit_list, key=lambda x:x[1])
    commit_message = ['```release-note']
    print("oldest timestamp is {} on commit {}".format(
        oldest_commit_timestamp[1].isoformat(), oldest_commit_timestamp[0]))
    pr_list = [pr for pr in get_pr_list()
               if oldest_commit_timestamp < pr['created_at']]
    print("pr's of interest:")
    for p in pr_list:
        # if the release note is None or the PR doesn't
        # have a release note, we don't need to include
        # anything about this PR in our note
        rn = parse_pr_body_for_release_note(p)
        created = datetime.strptime(p['created_at'], '%Y-%m-%dT%H:%M:%SZ')
        if rn and oldest_commit_timestamp[1] < created:
            print("found PR {} with date {} and release note '{}'".format(
                p['number'], created.isoformat(), rn))
            if pr_commit_in_commit_list(p['merge_commit_sha'], commit_list):
                print("Using pr {}".format(p['number']))
                commit_message.append(rn)
            else:
                print("No commit from PR in commit list to pull, skipping")
        else:
            if rn:
                print("skipping PR {} with time {} due to date".format(p['number'], datetime.strptime(p['created_at'], '%Y-%m-%dT%H:%M:%SZ').isoformat()))
            else:
                print("skipping PR {} with time {} due to lack of release note".format(p['number'], datetime.strptime(p['created_at'], '%Y-%m-%dT%H:%M:%SZ').isoformat()))

    commit_message.append("```\n")
    with open("pr_message.txt", "w") as text_file:
        str = "\n".join(commit_message)
        text_file.write(str)
        print("Commit message:")
        print(str)


write_pr_commit_message()
