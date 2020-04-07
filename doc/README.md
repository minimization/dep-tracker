# Buildroot Generator Workflow
![Buildroot Generator Workflow](https://github.com/minimization/dep-tracker/blob/master/doc/buildroot-generator-workflow.png)

## 1 Workloads tagged into ELN
Each workload contains the minimun packages needed to do whatever work is required.
The workloads that we want to build as RHEL, get tagged with an eln tag.

## 2 ELN Compose is build
The Feedback-Pipeline takes all the workloads that were tagged into ELN, and determines
what things would look like if they were all installed.  This determines what is required
to install the workloads.

## 3 ELN Compose output fed into buildroot-generator
The buildroot generator determines what it would take to build all the packages given it.
For this run, it is given the full output of the ELN Compose, and it determines the
buildroot, based on the Fedora Rawhide binary, and source repos.

## 4 buildroot-generator output used to identify Archful SRPMS
Some source rpm's have different build dependencies based on what architecture they were
built on.  We call these "Archful SRPMS".  The initial buildroot list is given to 
identify-archful-srpms and it determines what source rpms are "Archful".  It also caches
source rpms.

## 5 Source list, and Archful list, passed to create-srpm-repos

## 6 Archful source rpms built for each arch

## 7 Archful source rpm repo generated and used
create-srpm-repos creates a source rpm repo for each architecture.  These repo's are used
for the next buildroot-generator run through.
buildroot-generator looks at Fedora Rawhide for it's binary packages, but the newly generated
archful source rpm for it's source packages.

## 8 buildroot-generator output populates ELN-Buildroot workload
The output of buildroot generator is compared to the packages from the initial ELN Compose.
All new packages are added to the ELN-Buildroot workload in Feedback-Pipeline.

## 9 New ELN-Buildroot workload is tagged into ELN-Buildroot tag

## 10 ELN-Buildroot compose is built
The Feedback-Pipeline takes all the workloads from the original ELN tag, and the new
ELN-Buildroot tag, and creates a new compose.  The output from this compose have all the
packages needed to build and install the original ELN Compose.
