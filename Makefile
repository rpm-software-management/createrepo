PACKAGE = createrepo
VERSION = 0.4.2
SHELL = /bin/sh
top_srcdir = .
srcdir = .
prefix = /usr
exec_prefix = ${prefix}

bindir = ${exec_prefix}/bin
sbindir = ${exec_prefix}/sbin
libexecdir = ${exec_prefix}/libexec
datadir = ${prefix}/share
sysconfdir = ${prefix}/etc
sharedstatedir = ${prefix}/com
localstatedir = ${prefix}/var
libdir = ${exec_prefix}/lib
infodir = ${prefix}/info
docdir = 
includedir = ${prefix}/include
oldincludedir = /usr/include
mandir = ${prefix}/man

pkgdatadir = $(datadir)/$(PACKAGE)
pkglibdir = $(libdir)/$(PACKAGE)
pkgincludedir = $(includedir)/$(PACKAGE)
top_builddir = 

# all dirs
DIRS = $(DESTDIR)$(bindir) $(DESTDIR)$(sysconfdir) $(DESTDIR)$(pkgdatadir)


# INSTALL scripts 
INSTALL         = install -p --verbose 
INSTALL_BIN     = $(INSTALL) -m 755 
INSTALL_DIR     = $(INSTALL) -m 755 -d 
INSTALL_DATA    = $(INSTALL) -m 644 
INSTALL_MODULES = $(INSTALL) -m 755 -D 
RM              = rm -f

SUBDIRS = bin

MODULES = $(srcdir)/genpkgmetadata.py \
    	  $(srcdir)/dumpMetadata.py 

.SUFFIXES: .py .pyc
.py.pyc: 
	python -c "import py_compile; py_compile.compile($*.py)"


all: $(MODULES)
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir VERSION=$(VERSION) PACKAGE=$(PACKAGE); \
	done

check: 
	pychecker $(MODULES) || exit 0 

install: all installdirs
	$(INSTALL_MODULES) $(srcdir)/$(MODULES) $(DESTDIR)$(pkgdatadir)
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir install VERSION=$(VERSION) PACKAGE=$(PACKAGE); \
	done

installdirs:
	for dir in $(DIRS) ; do \
      $(INSTALL_DIR) $$dir ; \
	done


uninstall:
	for module in $(MODULES) ; do \
	  $(RM) $(pkgdatadir)/$$module ; \
	done
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir uninstall VERSION=$(VERSION) PACKAGE=$(PACKAGE); \
	done

clean:
	$(RM)  *.pyc *.pyo
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir clean VERSION=$(VERSION) PACKAGE=$(PACKAGE); \
	done

distclean: clean
	$(RM) -r .libs
	$(RM) core
	$(RM) *~
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir distclean VERSION=$(VERSION) PACKAGE=$(PACKAGE); \
	done

mostlyclean:
	$(MAKE) clean


maintainer-clean:
	$(MAKE) distclean
	$(RM) $(srcdir)/configure


dist:
	olddir=`pwd`; \
	distdir=$(PACKAGE)-$(VERSION); \
	$(RM) -r .disttmp; \
	$(INSTALL_DIR) .disttmp; \
	$(INSTALL_DIR) .disttmp/$$distdir; \
	$(MAKE) distfiles
	distdir=$(PACKAGE)-$(VERSION); \
	cd .disttmp; \
	tar -cvz > ../$$distdir.tar.gz $$distdir; \
	cd $$olddir
	$(RM) -r .disttmp

daily:
	olddir=`pwd`; \
	distdir=$(PACKAGE); \
	$(RM) -r .disttmp; \
	$(INSTALL_DIR) .disttmp; \
	$(INSTALL_DIR) .disttmp/$$distdir; \
	$(MAKE) dailyfiles
	day=`/bin/date +%Y%m%d`; \
	distdir=$(PACKAGE); \
	tarname=$$distdir-$$day ;\
	cd .disttmp; \
	perl -pi -e "s/\#DATE\#/$$day/g" $$distdir/$(PACKAGE)-daily.spec; \
	echo $$day; \
	tar -cvz > ../$$tarname.tar.gz $$distdir; \
	cd $$olddir
	$(RM) -rf .disttmp

dailyfiles:
	distdir=$(PACKAGE); \
	cp \
	$(srcdir)/*.py \
	$(srcdir)/Makefile \
	$(srcdir)/ChangeLog \
	$(srcdir)/README \
	$(srcdir)/$(PACKAGE).spec \
	$(top_srcdir)/.disttmp/$$distdir
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir dailyfiles VERSION=$(VERSION) PACKAGE=$(PACKAGE); \
	done

distfiles:
	distdir=$(PACKAGE)-$(VERSION); \
	cp \
	$(srcdir)/*.py \
	$(srcdir)/Makefile \
	$(srcdir)/ChangeLog \
	$(srcdir)/README \
	$(srcdir)/$(PACKAGE).spec \
	$(top_srcdir)/.disttmp/$$distdir
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir distfiles VERSION=$(VERSION) PACKAGE=$(PACKAGE); \
	done

archive: dist

.PHONY: todo
todo:
	@echo ---------------===========================================
	@grep -n TODO\\\|FIXME `find . -type f` | grep -v grep
	@echo ---------------===========================================
.PHONY: all install install-strip uninstall clean distclean mostlyclean maintainer-clean info dvi dist distfiles check installcheck installdirs daily dailyfiles
