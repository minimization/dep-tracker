# dep-tracker
Track dependencies for a given list of rpms across a given repo

# Setup
Copy the whole directory stucture to wherever you want.  This will be your work directory.
If you want the script, dep-tracker, to be in a seperate place from the work-directory, edit the WORK_DIR= line in dep-tracker to point wherever you have the work directory.

## conf - Configuration Files

### config.inc
Central configuration for all scripts.
Specific to dep-tracker are

#### DT_ACTION_LIST
What actions do you want to do if a change is seen.
Currently the only option is email, but in the future, there could be other actions.

#### EMAIL_LIST
List of emails to send changes to.
The list must be a comma seperated list of email addresses.

### Packages.<arch>
The list of packages we are working with.

### repos
A list of dnf repo's that the customers can use for checking against.  Currently, dep-tracker can only check against one repo.  So each repo file has just the one dnf repository, and it's source repository.
