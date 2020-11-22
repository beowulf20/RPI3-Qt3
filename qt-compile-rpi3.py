import git
import subprocess
from threading import Thread
import tarfile
import urllib
import os

QT_VERSION = "5.15.0"
QT_SRC_URL = "http://download.qt.io/archive/qt/5.15/{0}/single/qt-everywhere-src-{0}.tar.xz".format(
    QT_VERSION)
QT_SRC_FILENAME = "qt-everywhere-src-{0}.tar.xz".format(QT_VERSION)
QT_SRC_EXPANDED_FOLDER_NAME = "qt-everywhere-src-{0}".format(QT_VERSION)

RPI_VERSION = "linux-rasp-pi-g++"
RPI_TOOLS_URL = "https://releases.linaro.org/components/toolchain/binaries/7.4-2019.02/arm-linux-gnueabihf/gcc-linaro-7.4.1-2019.02-x86_64_arm-linux-gnueabihf.tar.xz"
RPI_TOOLS_EXPANDED_FOLDER_NAME = "gcc-linaro-7.4.1-2019.02-x86_64_arm-linux-gnueabihf"

RPI_SSH_HOSTNAME = "192.168.1.41"
RPI_SSH_USERNAME = "pi"
RPI_SSH_COMMAND = 'ssh {1} -l {0} -o BatchMode=yes $@'.format(
    RPI_SSH_USERNAME, RPI_SSH_HOSTNAME).split(' ')
RPI_BASE_FOLDER = '/home/pi/qt{0}pi'.format(QT_VERSION)

LOCAL_BASE_PATH = "{}/tmp/{}".format(os.getcwd(), RPI_VERSION)

SYSROOT_FIX_SCRIPT_URL = "https://raw.githubusercontent.com/riscv/riscv-poky/master/scripts/sysroot-relativelinks.py"

MAKE_N_CORES = 8


def fetch_file(url, filename):
    subprocess.run('wget {} -nc -q -O {}'.format(url, filename).split(' '))


def fetch_tar(url, path, tempName):
    subprocess.run(
        ['mkdir', '-p', path])
    subprocess.run(['wget', url,
                    '-nc', '-q', "-O", "{}/{}".format(path, tempName)])
    subprocess.run(['tar', 'xf', "{}/{}".format(path, tempName),
                    "-C", path,  "--skip-old-files"])


def fetch_rpi_toolchain():
    path = "{}/tools".format(LOCAL_BASE_PATH)
    fetch_tar(RPI_TOOLS_URL, path, 'rpitools.tar.xz')
    print("Downloading toolchain for {}".format(RPI_VERSION))


def fetch_qt_sources():
    print("Downloading source code for qt v{}".format(QT_VERSION))
    fetch_tar(QT_SRC_URL, LOCAL_BASE_PATH, QT_SRC_FILENAME)


def update_mkspecs():
    print("Updating mkspecs errors")
    path = "{}/{}".format(LOCAL_BASE_PATH, QT_SRC_EXPANDED_FOLDER_NAME)
    srcPath = "{}/qtbase/mkspecs/linux-arm-gnueabi-g++".format(path)
    dstPath = "{}/qtbase/mkspecs/linux-arm-gnueabihf-g++".format(path)
    cmds = "cp -R {0} {1}".format(srcPath, dstPath)
    subprocess.run(cmds.split(' '))
    cmds = 'sed -i -e "s/arm-linux-gnueabi-/arm-linux-gnueabihf-/g" {0}/qmake.conf'.format(
        dstPath)
    subprocess.call([cmds], shell=True)


def create_req_dirs():
    print("Creating required directories...")
    cmd = "mkdir -p {0}/build {0}/tools {0}/sysroot {0}/sysroot/usr {0}/sysroot/opt".format(
        LOCAL_BASE_PATH).split(' ')
    subprocess.run(cmd)
    pass


def ssh_execute_command(cmd):
    d = subprocess.run(RPI_SSH_COMMAND+cmd.split(' '))
    if d.returncode != 0:
        print("Failed to execute: '{0}' at {1}@{2}".format(cmd,
                                                           RPI_SSH_USERNAME, RPI_SSH_HOSTNAME))
        os._exit(d.returncode)


def ssh_check_access():
    d = subprocess.run(RPI_SSH_COMMAND+['true'])
    if d.returncode != 0:
        print("Failed to access {}@{}".format(RPI_SSH_USERNAME, RPI_SSH_HOSTNAME))
        os._exit(d.returncode)


def rpi_rsync_sysroot():
    print("rsyncing '{0}/sysroot' with {1}@{2}".format(LOCAL_BASE_PATH,
                                                       RPI_SSH_USERNAME, RPI_SSH_HOSTNAME))

    cmd1 = 'rsync -azq {0}@{1}:/lib {2}/sysroot'.format(
        RPI_SSH_USERNAME, RPI_SSH_HOSTNAME, LOCAL_BASE_PATH).split(' ')
    cmd2 = 'rsync -azq {0}@{1}:/usr/include {2}/sysroot/usr'.format(
        RPI_SSH_USERNAME, RPI_SSH_HOSTNAME, LOCAL_BASE_PATH).split(' ')
    cmd3 = 'rsync -azq {0}@{1}:/usr/lib {2}/sysroot/usr'.format(
        RPI_SSH_USERNAME, RPI_SSH_HOSTNAME, LOCAL_BASE_PATH).split(' ')
    cmd4 = 'rsync -azq {0}@{1}:/opt/vc {2}/sysroot/opt'.format(
        RPI_SSH_USERNAME, RPI_SSH_HOSTNAME, LOCAL_BASE_PATH).split(' ')

    ps = [subprocess.Popen(cmd1), subprocess.Popen(
        cmd2), subprocess.Popen(cmd3), subprocess.Popen(cmd4)]
    [p.wait() for p in ps]
    print('rsync finished')


def fix_rsync_sysroot_links():
    print('fixing sysroot links....')
    subprocess.run("sudo chmod +x {0}/sysroot-fix.py && python {0}/sysroot-fix.py sysroot".format(LOCAL_BASE_PATH).split(' '),
                   cwd=LOCAL_BASE_PATH)


def qt_configure():
    args = "../{0}/configure -release \
		-opengl es2 \
        -eglfs \
		-device {1} \
		-device-option CROSS_COMPILE={2}/tools/{3}/bin/arm-linux-gnueabihf- \
		-sysroot {2}/sysroot \
		-prefix /usr/local/qt5.15 \
		-extprefix {2}/qt5.15 \
		-opensource \
		-confirm-license \
		-skip qtscript \
		-skip qtwayland \
		-skip qtwebengine \
		-nomake tests \
		-make libs \
		-pkg-config \
		-no-use-gold-linker \
		-v \
		-recheck".format(QT_SRC_EXPANDED_FOLDER_NAME,
                   RPI_VERSION,
                   LOCAL_BASE_PATH,
                   RPI_TOOLS_EXPANDED_FOLDER_NAME
                   ).replace('\t', '').replace('\n', '').split(' ')

    d = subprocess.run(cwd='{}/build'.format(LOCAL_BASE_PATH), args=args)
    if d.returncode != 0:
        print("Failed to configure qt{}".format(QT_VERSION))
        os._exit(d.returncode)


def qt_build():
    d = subprocess.run(cwd=LOCAL_BASE_PATH+'/build',
                       args='sudo make -j {0}'.format(MAKE_N_CORES).split(' '))
    if d.returncode != 0:
        print("Failed to build qt{}".format(QT_VERSION))
        os._exit(d.returncode)


def qt_install():
    d = subprocess.run(cwd=LOCAL_BASE_PATH+'/build',
                       args='make install -j {0}'.format(MAKE_N_CORES).split(' '))
    if d.returncode != 0:
        print("Failed to install qt{}".format(QT_VERSION))
        os._exit(d.returncode)
    pass


if __name__ == "__main__":
    create_req_dirs()

    qtSrcThread = Thread(target=fetch_qt_sources)
    rpiToolsThread = Thread(target=fetch_rpi_toolchain)
    sysrootfixThread = Thread(target=fetch_file, args=(
        SYSROOT_FIX_SCRIPT_URL, '{}/sysroot-fix.py'.format(LOCAL_BASE_PATH)))
    qtSrcThread.start()
    rpiToolsThread.start()
    sysrootfixThread.start()

    rpiToolsThread.join()
    qtSrcThread.join()
    sysrootfixThread.join()

    print("Finished all required downloads")

    update_mkspecs()

    ssh_check_access()
    ssh_execute_command('mkdir -p ' + RPI_BASE_FOLDER)
    rpi_rsync_sysroot()
    fix_rsync_sysroot_links()
    qt_configure()
    qt_build()
    qt_install()

    print('Hopefully everything is finished and well configured! Enjoy :)')
    os._exit(0)
