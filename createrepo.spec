Summary: Creates a common metadata repository
Name: createrepo
Version: 0.3
Release: 1
License: GPL
Group: System Environment/Base
Source: %{name}-%{version}.tar.gz
URL: http://linux.duke.edu/metadata/
BuildRoot: %{_tmppath}/%{name}-%{version}root
BuildArchitectures: noarch
Requires: python >= 2.1, rpm-python, rpm >= 0:4.1.1, libxml2-python

%description
This utility will generate a common metadata repository from a directory of
rpm packages

%prep
%setup -q

%install
[ "$RPM_BUILD_ROOT" != "/" ] && rm -rf $RPM_BUILD_ROOT
%makeinstall

%clean
[ "$RPM_BUILD_ROOT" != "/" ] && rm -rf $RPM_BUILD_ROOT


%files
%defattr(-, root, root)
%dir %{_datadir}/%{name}
%doc ChangeLog README
%{_datadir}/%{name}/*
%{_bindir}/%{name}

%changelog
* Sun Jan 18 2004 Seth Vidal <skvidal@phy.duke.edu>
- 0.3

* Tue Jan 13 2004 Seth Vidal <skvidal@phy.duke.edu>
- 0.2 - 

* Sat Jan 10 2004 Seth Vidal <skvidal@phy.duke.edu>
- first packaging

