SHELL = /bin/sh
top_srcdir = ..
srcdir = ../docs
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
top_builddir = ../

# all dirs
DIRS = $(DESTDIR)$(bindir) $(DESTDIR)/etc $(DESTDIR)$(pkgdatadir)


# INSTALL scripts 
INSTALL         = install -p --verbose 
INSTALL_BIN     = $(INSTALL) -m 755 
INSTALL_DIR     = $(INSTALL) -m 755 -d 
INSTALL_DATA    = $(INSTALL) -m 644 
INSTALL_MODULES = $(INSTALL) -m 755 -D 
RM 		= rm -f


all: 
	echo "nothing to do"


install: all installdirs
	mkdir -p $(DESTDIR)/usr/share/man/man8
	$(INSTALL_DATA) createrepo.8 $(DESTDIR)/usr/share/man/man8/creatrepo.8


uninstall:
	$(RM) $(bindir)/$(PACKAGE)



clean:


distclean:
	$(RM) -rf .libs
	$(RM) -f core
	$(RM) -f *~


mostlyclean:
	$(MAKE) clean


maintainer-clean:
	$(MAKE) distclean


distfiles:
	distdir=$(PACKAGE)-$(VERSION); \
	mkdir $(top_srcdir)/.disttmp/$$distdir/docs;\
	cp \
	$(srcdir)/createrepo.8 \
	$(srcdir)/Makefile \
	$(top_srcdir)/.disttmp/$$distdir/docs

dailyfiles:
	distdir=$(PACKAGE); \
	mkdir $(top_srcdir)/.disttmp/$$distdir/docs;\
	cp \
	$(srcdir)/createrepo.8 \
	$(srcdir)/Makefile \
	$(top_srcdir)/.disttmp/$$distdir/docs

installdirs:
	$(MAKE) -C $(top_srcdir) installdirs


.PHONY: all install install-strip uninstall clean distclean mostlyclean maintainer-clean info dvi dist distfiles check installcheck installdirs dailyfiles



