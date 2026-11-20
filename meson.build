project(
  'exam-pool',
  version: '0.1.2',
  license: 'GPL-3.0-or-later',
  meson_version: '>=0.63',
)

py = import('python').find_installation('python3')
datadir = get_option('datadir')
bindir = get_option('bindir')
py_install_dir = py.get_install_dir()

py.install_sources(
  'src/exam_pool/__init__.py',
  'src/exam_pool/__main__.py',
  'src/exam_pool/application.py',
  'src/exam_pool/paths.py',
  'src/exam_pool/settings.py',
  subdir: 'exam_pool',
)

py.install_sources(
  'src/exam_pool/domain/__init__.py',
  'src/exam_pool/domain/exam.py',
  'src/exam_pool/domain/models.py',
  'src/exam_pool/domain/study_queue.py',
  subdir: 'exam_pool/domain',
)

py.install_sources(
  'src/exam_pool/data/__init__.py',
  'src/exam_pool/data/database.py',
  'src/exam_pool/data/packs.py',
  'src/exam_pool/data/updates.py',
  subdir: 'exam_pool/data',
)

py.install_sources(
  'src/exam_pool/ui/__init__.py',
  'src/exam_pool/ui/chart.py',
  'src/exam_pool/ui/common.py',
  'src/exam_pool/ui/dialogs.py',
  'src/exam_pool/ui/home.py',
  'src/exam_pool/ui/preferences.py',
  'src/exam_pool/ui/stats.py',
  'src/exam_pool/ui/study.py',
  'src/exam_pool/ui/test.py',
  'src/exam_pool/ui/window.py',
  subdir: 'exam_pool/ui',
)

install_subdir(
  'src/exam_pool/resources',
  install_dir: py_install_dir / 'exam_pool',
  exclude_files: ['gschemas.compiled'],
)

schemas = custom_target(
  'gschemas.compiled',
  input: 'src/exam_pool/settings.gschema.xml',
  output: 'gschemas.compiled',
  command: [
    'glib-compile-schemas',
    '--targetdir', '@OUTDIR@',
    meson.current_source_dir() / 'src' / 'exam_pool',
  ],
  install: true,
  install_dir: datadir / 'glib-2.0/schemas',
)

install_data(
  'data/io.github.jeangrenouille010101.ExamPool.desktop',
  install_dir: datadir / 'applications',
)

install_data(
  'data/io.github.jeangrenouille010101.ExamPool.metainfo.xml',
  install_dir: datadir / 'metainfo',
)

install_data(
  'data/exam-pool',
  install_dir: bindir,
  install_mode: 'rwxr-xr-x',
)
