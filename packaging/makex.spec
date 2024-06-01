%{?!python3_pkgversion:%global python3_pkgversion 3}
# Builds a package per Fedora/RHEL specifications:
# - Source Only
# - Uses platform python

Name:           makex
Version:        %{version}
Release:        1%{?dist}
Summary:        Build/Automation tool
License:        MetaCompany
URL:            http://makex.tools
Source0:        makex-source.zip
Source1:        makex.sh

BuildArch:      noarch

Requires:       python >= 3.9
Requires:       python-toml

BuildRequires:  python%{python3_pkgversion}-devel
BuildRequires:  python%{python3_pkgversion}-setuptools

%{?python_enable_dependency_generator}

%description

Makex is a build/automation tool.

%prep
%setup -c makex


%build


%install
rm -rf $RPM_BUILD_ROOT

mkdir -p $RPM_BUILD_ROOT%{python3_sitelib}/
mkdir -p $RPM_BUILD_ROOT%{_bindir}/

#cp %{SOURCE1} $RPM_BUILD_ROOT/%{_bindir}/
#chmod +x $RPM_BUILD_ROOT/%{_bindir}/makex
install -m 755 %{SOURCE1} $RPM_BUILD_ROOT%{_bindir}/makex

cp -r python/makex $RPM_BUILD_ROOT%{python3_sitelib}/


%check
# use what your upstream is using
#{__python3} setup.py test
#{__python3} -m pytest
#{__python3} -m nose


%files
#doc add-docs-here
#license add-license-file-here
%{_bindir}/makex
%{python3_sitelib}/makex/**.py
%{python3_sitelib}/makex/data/completions/makex.bash
%{python3_sitelib}/makex/data/completions/makex.zsh
%{python3_sitelib}/makex/integrations/intellij.py
%{python3_sitelib}/makex/integrations/vscode.py
%{python3_sitelib}/makex/platform_object/__init__.py
%{python3_sitelib}/makex/platform_object/platform_object.py
%{python3_sitelib}/makex/platform_object/platform_test.py
#{python3_sitelib}/{srcname}-{version}-py{python3_version}.egg-info/

# For arch-specific packages: sitearch
#{python3_sitearch}/{srcname}/


%changelog
* Sat Jun 01 2024 Nate Skulic <nateskulic@users.noreply.github.com>
- 
