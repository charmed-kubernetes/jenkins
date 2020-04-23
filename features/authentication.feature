Feature: Authentication
  Make sure that any changes made to the basic authentication
  csv file will be modified on the master and then propagated over to the
  other masters in the cluster.

  Scenario: Propagate auth file to mutiple masters
    Updates /root/cdk/basic_auth.csv on a single master and then makes sure the
    other masters in the cluster receive those updates
    Given we make a change to basic_auth.csv
    Then we make sure those changes propogate to other masters
