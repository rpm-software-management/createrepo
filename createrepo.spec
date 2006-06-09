Summary: Creates a common metadata repository
Name: createrepo
Version: 0.4.5
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
%{_mandir}/man8/createrepo.8*

%changelog
* Fri Jun  9 2006 Seth Vidal <skvidal at linux.duke.edu>
- 0.4.5

* Sat Mar 04 2006 Paul Nasrat <pnasrat@redhat.com>
- 0.4.4

* Thu Jul 14 2005 Seth Vidal <skvidal@phy.duke.edu>
- enable caching option
- 0.4.3

* Tue Jan 18 2005 Seth Vidal <skvidal@phy.duke.edu>
- add man page

* Mon Jan 17 2005 Seth Vidal <skvidal@phy.duke.edu>
- 0.4.2


* Thu Oct 21 2004 Seth Vidal <skvidal@phy.duke.edu>
- ghost files not being added into primary file list if 
  matching regex
- 0.4.1


* Mon Oct 11 2004 Seth Vidal <skvidal@phy.duke.edu>
- 0.4.0

* Thu Sep 30 2004 Seth Vidal <skvidal@phy.duke.edu>
- 0.3.9
- fix for groups checksum creation

* Sat Sep 11 2004 Seth Vidal <skvidal@phy.duke.edu>
- 0.3.8

* Wed Sep  1 2004 Seth Vidal <skvidal@phy.duke.edu>
- 0.3.7

* Fri Jul 23 2004 Seth Vidal <skvidal@phy.duke.edu>
- make filelists right <sigh>


* Fri Jul 23 2004 Seth Vidal <skvidal@phy.duke.edu>
- fix for broken filelists

* Mon Jul 19 2004 Seth Vidal <skvidal@phy.duke.edu>
- re-enable groups
- update num to 0.3.4

* Tue Jun  8 2004 Seth Vidal <skvidal@phy.duke.edu>
- update to the format
- versioned deps
- package counts
- uncompressed checksum in repomd.xml


* Fri Apr 16 2004 Seth Vidal <skvidal@phy.duke.edu>
- 0.3.2 - small addition of -p flag

* Sun Jan 18 2004 Seth Vidal <skvidal@phy.duke.edu>
- I'm an idiot

* Sun Jan 18 2004 Seth Vidal <skvidal@phy.duke.edu>
- 0.3

* Tue Jan 13 2004 Seth Vidal <skvidal@phy.duke.edu>
- 0.2 - 

* Sat Jan 10 2004 Seth Vidal <skvidal@phy.duke.edu>
- first packaging

