import pytest
from ..snapapi import latest, max_rev


revisions = [['1110',
  '2019-07-24T18:28:37Z',
  's390x',
  '1.13.8',
  '1.13/edge*, 1.13/candidate*, 1.13/beta*'],
 ['1107',
  '2019-07-24T18:22:18Z',
  's390x',
  '1.15.1',
  '1.15/edge*, 1.15/candidate*, 1.15/beta*'],
 ['1105',
  '2019-07-24T18:21:08Z',
  's390x',
  '1.14.4',
  '1.14/edge*, 1.14/candidate*, 1.14/beta*'],
 ['1098',
  '2019-07-24T14:52:31Z',
  's390x',
  '1.15.1',
  '1.15/edge, 1.15/candidate, 1.15/beta'],
 ['1089', '2019-07-23T20:34:56Z', 's390x', '1.14.4', '1.14/beta'],
 ['1088', '2019-07-23T20:34:53Z', 's390x', '1.13.8', '1.13/beta'],
 ['1067', '2019-07-08T23:45:48Z', 's390x', '1.13.8', '1.13/edge'],
 ['1054', '2019-06-28T14:04:56Z', 's390x', '1.15.0', '1.15/edge'],
 ['1040', '2019-06-21T23:50:32Z', 's390x', '1.13.7', '1.13/edge'],
 ['1033',
  '2019-06-21T13:09:13Z',
  's390x',
  '1.15.0',
  '1.15/edge, 1.15/beta, 1.15/candidate, beta*, candidate*, 1.15/stable*, '
  'stable*'],
 ['1032',
  '2019-06-20T17:26:24Z',
  's390x',
  '1.15.0',
  '1.15/edge, edge*, beta, candidate, 1.15/beta, 1.15/candidate'],
 ['1026', '2019-06-19T23:48:51Z', 's390x', '1.15.0', '1.15/edge'],
 ['1018',
  '2019-06-07T17:22:48Z',
  's390x',
  '1.13.7',
  '1.13/edge, 1.13/beta, 1.13/candidate, 1.13/stable*'],
 ['1010',
  '2019-06-06T17:23:11Z',
  's390x',
  '1.14.3',
  '1.14/edge, edge, beta, candidate, 1.14/beta, 1.14/candidate, stable, '
  '1.14/stable*'],
 ['1003',
  '2019-05-28T17:24:52Z',
  's390x',
  '1.12.9',
  '1.12/edge*, 1.12/beta*, 1.12/candidate*, 1.12/stable*'],
 ['1001',
  '2019-05-17T17:24:01Z',
  's390x',
  '1.14.2',
  '1.14/edge, edge, beta, candidate, 1.14/beta, 1.14/candidate, 1.14/stable, '
  'stable'],
 ['990',
  '2019-05-08T17:26:05Z',
  's390x',
  '1.13.6',
  '1.13/edge, 1.13/beta, 1.13/candidate, 1.13/stable'],
 ['966',
  '2019-04-24T17:27:57Z',
  's390x',
  '1.12.8',
  '1.12/edge, 1.12/beta, 1.12/candidate, 1.12/stable'],
 ['961',
  '2019-04-22T16:13:17Z',
  's390x',
  '1.14.1',
  '1.14/edge/test-k8s-source'],
 ['957',
  '2019-04-22T15:04:49Z',
  's390x',
  '1.14.1',
  '1.14/edge/test-k8s-source'],
 ['953',
  '2019-04-19T20:48:31Z',
  's390x',
  '1.14.1',
  '1.14/edge/test-k8s-source'],
 ['949',
  '2019-04-18T14:49:17Z',
  's390x',
  '1.14.1',
  '1.14/edge/test-k8s-source'],
 ['941',
  '2019-04-16T19:18:13Z',
  's390x',
  '1.14.1',
  '1.14/edge/test-k8s-source']]


def test_latest_rev_115():
    """ Make sure we pull latest revision
    """
    output = max_rev(revisions, '1.15')
    # latest("kubectl", "1.14", "s390x", True)
    assert output is not None
    assert output == 1107


def test_latest_rev_114():
    """ Make sure we pull latest revision
    """
    output = max_rev(revisions, '1.14')
    # latest("kubectl", "1.14", "s390x", True)
    assert output is not None
    assert output == 1105


def test_latest_rev_113():
    """ Make sure we pull latest revision
    """
    output = max_rev(revisions, '1.13')
    # latest("kubectl", "1.14", "s390x", True)
    assert output is not None
    assert output == 1110
