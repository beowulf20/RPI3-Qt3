import git
import subprocess
from threading import Thread
import tarfile
import urllib
import os

QT_VERSION = "5.15"
QT_SRC_EXPANDED_FOLDER_NAME = "qt5"
RPI_VERSION = "linux-rasp-pi3-g++"
RPI_TOOLS_URL = "https://releases.linaro.org/components/toolchain/binaries/7.5-2019.12/arm-linux-gnueabihf/gcc-linaro-7.5.0-2019.12-x86_64_arm-linux-gnueabihf.tar.xz"
RPI_TOOLS_EXPANDED_FOLDER_NAME = "gcc-linaro-7.5.0-2019.12-x86_64_arm-linux-gnueabihf"
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
    subprocess.run('git clone --quiet https://github.com/qt/qt5.git'.split(' '),
                   cwd=LOCAL_BASE_PATH)
    subprocess.run('git checkout {0}'.format(
        QT_VERSION).split(' '), cwd=LOCAL_BASE_PATH+'/qt5')
    subprocess.run(
        './init-repository --module-subset=essential'.split(' '), cwd=LOCAL_BASE_PATH+'/qt5')


def update_mkspecs():
    print("Updating mkspecs errors")
    subprocess.run('cp -f {0}/rpi3-g++-qmake.conf linux-rasp-pi3-g++/qmake.conf'.format(os.getcwd()).split(
        ' '), cwd="{0}/qt5/qtbase/mkspecs/devices".format(LOCAL_BASE_PATH))


def create_req_dirs():
    print("Creating required directories...")
    dirs = list(map(lambda d: '{0}/{1}'.format(LOCAL_BASE_PATH, d), [
        "build",
        "tools",
        "sysroot",
        "sysroot/usr",
        "sysroot/opt",
        "sysroot/usr/share/pkgconfig"
    ]))
    cmd = ["mkdir", "-p"]+dirs
    subprocess.run(cmd)
    pass


def ssh_execute_command(cmd):
    d = subprocess.run(RPI_SSH_COMMAND+cmd.split(' '))
    if d.returncode != 0:
        print("Failed to execute: '{0}' at {1}@{2}".format(cmd,
                                                           RPI_SSH_USERNAME, RPI_SSH_HOSTNAME))
        os._exit(d.returncode)


def ssh_check_access():
    print("Checking if host has ssh access to {0}@{1}".format(
        RPI_SSH_USERNAME,
        RPI_SSH_HOSTNAME
    ))
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
    cmd5 = 'rsync -azq {0}@{1}:/usr/share/pkgconfig {2}/sysroot/usr/share'.format(
        RPI_SSH_USERNAME, RPI_SSH_HOSTNAME, LOCAL_BASE_PATH).split(' ')

    ps = [subprocess.Popen(cmd1), subprocess.Popen(
        cmd2), subprocess.Popen(cmd3), subprocess.Popen(cmd4), subprocess.Popen(cmd5)]
    [p.wait() for p in ps]
    fix_rsync_sysroot_links()
    print('rsync finished')


def fix_rsync_sysroot_links():
    print('fixing sysroot links....')
    subprocess.run("sudo chmod +x {0}/sysroot-fix.py".format(LOCAL_BASE_PATH).split(' '),
                   cwd=LOCAL_BASE_PATH).check_returncode()
    subprocess.run("python {0}/sysroot-fix.py sysroot".format(LOCAL_BASE_PATH).split(' '),
                   cwd=LOCAL_BASE_PATH).check_returncode()


def fix_pkg_filenames():
    subprocess.run('mv egl.pc egl.pc.mesa'.split(
        ' '),
        cwd='{0}/sysroot/usr/lib/arm-linux-gnueabihf/pkgconfig'.format(LOCAL_BASE_PATH)).check_returncode()
    subprocess.run('mv glesv2.pc glesv2.pc.mesa'.split(
        ' '),
        cwd='{0}/sysroot/usr/lib/arm-linux-gnueabihf/pkgconfig'.format(LOCAL_BASE_PATH)).check_returncode()
    pass


def qt_configure():
    args = "../{0}/configure -release \
		-opengl es2 \
        -eglfs \
		-device {1} \
		-device-option CROSS_COMPILE={2}/tools/{3}/bin/arm-linux-gnueabihf- \
		-sysroot {2}/sysroot \
		-prefix /usr/local/qt{4} \
		-extprefix {2}/qt{4}-target-binaries \
        -hostprefix {2}/qt{4}-host-binaries \
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
                   RPI_TOOLS_EXPANDED_FOLDER_NAME,
                   QT_VERSION
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


def prompt_sudo():
    ret = 0
    if os.geteuid() != 0:
        msg = "[sudo] password for %u:"
        ret = subprocess.check_call("sudo -v -p '%s'" % msg, shell=True)
    if ret != 0:
        print('you must be sudo to avoid pain the asses')
        os._exit(ret)


def rsync_pi_target_binaries():
    print("rsyncing recently built binaries to {0}@{1}".format(
        RPI_SSH_USERNAME,
        RPI_SSH_HOSTNAME
    ))
    subprocess.run(
        'rsync -azq {2}/qt{3}-target-binaries {0}@{1}:/usr/local/qt5pi/'.format(
            RPI_SSH_USERNAME,
            RPI_SSH_HOSTNAME,
            LOCAL_BASE_PATH,
            QT_VERSION).split(' '))


if __name__ == "__main__":
    prompt_sudo()
    ssh_check_access()
    create_req_dirs()

    qtSrcThread = Thread(target=fetch_qt_sources)
    qtSrcThread.start()

    rpiToolsThread = Thread(target=fetch_rpi_toolchain)
    rpiToolsThread.start()

    sysrootfixThread = Thread(target=fetch_file, args=(
        SYSROOT_FIX_SCRIPT_URL, '{}/sysroot-fix.py'.format(LOCAL_BASE_PATH)))
    sysrootfixThread.start()

    rSyncThread = Thread(target=rpi_rsync_sysroot)
    rSyncThread.start()

    rpiToolsThread.join()
    qtSrcThread.join()
    sysrootfixThread.join()
    rSyncThread.join()

    print("Finished all required downloads")

    update_mkspecs()

    ssh_execute_command('mkdir -p ' + RPI_BASE_FOLDER)

    fix_pkg_filenames()
    qt_configure()
    qt_build()
    qt_install()
    rsync_pi_target_binaries()

    print('Hopefully everything is finished and well configured! Enjoy :)')
    os._exit(0)
