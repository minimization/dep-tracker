# dep-tracker
Track dependencies for a given list of rpms across a given repo

= Setup
Copy the whole directory stucture to wherever you want.  This will be your work directory.
If you want the script, dep-tracker, to be in a seperate place from the work-directory, edit the WORK_DIR= line in dep-tracker to point wherever you have the work directory.
== WorkSpace Directories
=== customers
Each customer has their own sub-directory in the customers directory.
In each customers sub-directory is that customers dt.conf and package list.
AFter dep-tracker has been run once, it will put log, archive, and other directories in the customers sub-directory.
=== repos
A list of dnf repo's that the customers can use for checking against.  Currently, dep-tracker can only check against one repo.  So each repo file has just the one dnf repository, and it's source repository.
== Dependencies
The following are requires to run dep-tracker
* dnf
* diff
* comm

= Customer Configuration Files

== package.list
A space seperated list of package names you want tracked.  These are built packages and/or sub-packages.  They are not source packages.
Do not put the version or release on the package, just the name.

== dt.conf
=== Repo
What repo you want to track your packages in.
This is not your system repo's, it is the repo's in the dt-tracker repo directory

=== Checks
What checks do you want to do on your list of packages.
==== package (Always done - no need to list it)
Check if the package.list has changed.
==== package-nvr
Check if the Name-Version-Release (NVR) of the packages in the package.list has changed.
==== package-deps
Check if any of the package dependencies change.  This only checks if a package has been added or removed from the dependency list.  It does not check if a version or release of any of the packages have changed.
==== package-deps-nvr
Check if any part of the package dependencies change.  This inclused version or release changes, as well as if packages have been added or removed.  If this check is chosen, you usually do not need to also do package-deps.
==== source-nvr
Check if the Name-Version-Release (NVR) of the source packages of the packages in the package.list has changed.
==== source-deps
Check if any dependencies needed to build the packages in the package.list has changed.  This only checks if a source package has been added or removed from the dependency list.  It does not check if a version or release of any of the source packages have changed.
==== source-deps-nvr
Check if any part of the dependencies needed to build the packages in the package.list has changed.  This inclused version or release changes, as well as if source packages have been added or removed.  If this check is chosen, you usually do not need to also do source-deps.

=== Action
What actions do you want to do if a change is seen.
Currently the only option is email, but in the future, there could be other actions.
==== email
Send an email with all the changes to list of emails.

=== Email
List of emails to send changes to.
The list must be a comma seperated list of email addresses.


= Tips
== Order of items in Checks
If you are doing multiple different checks of both packages and source, group the package and source checks together in the list.  Such as "Checks: package-deps package-deps-nvr source-deps source-deps-nvr".  This will make the checks go much faster.
