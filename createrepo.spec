%{!?python_sitelib: %define python_sitelib %(python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

Summary: Creates a common metadata repository
Name: createrepo
Version: 0.9.5
Release: 1
License: GPL
Group: System Environment/Base
Source: %{name}-%{version}.tar.gz
URL: http://linux.duke.edu/metadata/
BuildRoot: %{_tmppath}/%{name}-%{version}root
BuildArchitectures: noarch
Requires: python >= 2.1, rpm-python, rpm >= 0:4.1.1, libxml2-python
Requires: yum-metadata-parser, yum >= 3.2.19

%description
This utility will generate a common metadata repository from a directory of
rpm packages

%prep
%setup -q

%install
[ "$RPM_BUILD_ROOT" != "/" ] && rm -rf $RPM_BUILD_ROOT
make DESTDIR=$RPM_BUILD_ROOT install

%clean
[ "$RPM_BUILD_ROOT" != "/" ] && rm -rf $RPM_BUILD_ROOT


%files
%defattr(-, root, root)
%dir %{_datadir}/%{name}
%doc ChangeLog README COPYING COPYING.lib
%{_datadir}/%{name}/*
%{_bindir}/%{name}
%{_bindir}/modifyrepo
%{_mandir}/man8/createrepo.8*
%{_mandir}/man1/modifyrepo.1*
%{python_sitelib}/createrepo

%changelog
* Mon Feb 18 2008 Seth Vidal <skvidal at fedoraproject.org>
- 0.9.5

* Mon Jan 28 2008 Seth Vidal <skvidal at fedoraproject.org>
- 0.9.4

* Tue Jan 22 2008 Seth Vidal <skvidal at fedoraproject.org>
- 0.9.3

* Thu Jan 17 2008 Seth Vidal <skvidal at fedoraproject.org>
- significant api changes

* Tue Jan  8 2008 Seth Vidal <skvidal at fedoraproject.org>
- 0.9.1 - lots of fixes
- cleanup changelog, too

* Thu Dec 20 2007 Seth Vidal <skvidal at fedoraproject.org>
- beginning of the new version

