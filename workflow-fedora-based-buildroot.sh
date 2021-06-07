./run.sh $@

#####
# Variables
#####
WORK_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source ${WORK_DIR}/conf/config.inc
VIEW=${REPO_BASE}
PACKAGELIST_DIR="${WORK_DIR}/packagelists-${REPO_BASE}"

# Upload to feedback-pipeline
if ! [ -d ${GIT_DIR}/content-resolver-input-additional ] ; then
  mkdir -p ${GIT_DIR}
  cd ${GIT_DIR}
  git clone git@github.com:minimization/content-resolver-input-additional.git
fi
if ! [ -d ${GIT_DIR}/content-resolver-input-additional ] ; then
  echo
  echo "You do not seem to have correct credentials for the git repo"
  echo "Exiting so you do no harm"
  echo
  exit 5
fi
cd ${GIT_DIR}/content-resolver-input-additional/configs
git pull
cp ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml .
git add ${VIEW}-buildroot-workload.yaml
git commit -m "Update ${VIEW}-buildroot-workload $(date +%Y-%m-%d-%H:%M)"
cp ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml .
git add buildroot-${VIEW}.yaml
git commit -m "Update buildroot-${VIEW}.yaml $(date +%Y-%m-%d-%H:%M)"
for this_arch in ${ARCH_LIST[@]}
do
  DATA_DIR="${DATA_DIR_BASE}/${this_arch}/${NEW_DIR}"
  cp ${DATA_DIR}/buildroot-package-relations--view-${VIEW}--${this_arch}.json .
done
git add buildroot-package-relations*
git commit -m "Update buildroot-package-relations json $(date +%Y-%m-%d-%H:%M)"
git push


exit 0

