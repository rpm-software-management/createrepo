# bash completion for createrepo and friends

_cr_createrepo()
{
    COMPREPLY=()

    case $3 in
        --version|-h|--help|-u|--baseurl|--distro|--content|--repo|--workers|\
        --revision|-x|--excludes|--changelog-limit|--max-delta-rpm-size)
            return 0
            ;;
        --basedir|-c|--cachedir|--update-md-path|-o|--outputdir|\
        --oldpackagedirs)
            COMPREPLY=( $( compgen -d -- "$2" ) )
            return 0
            ;;
        -g|--groupfile)
            COMPREPLY=( $( compgen -f -o plusdirs -X '!*.xml' -- "$2" ) )
            return 0
            ;;
        -s|--sumtype)
            COMPREPLY=( $( compgen -W 'md5 sha1 sha256 sha512' -- "$2" ) )
            return 0
            ;;
        -i|--pkglist|--read-pkgs-list)
            COMPREPLY=( $( compgen -f -o plusdirs -- "$2" ) )
            return 0
            ;;
        -n|--includepkg)
            COMPREPLY=( $( compgen -f -o plusdirs -X '!*.rpm' -- "$2" ) )
            return 0
            ;;
        --num-deltas)
            COMPREPLY=( $( compgen -W '1 2 3 4 5 6 7 8 9' -- "$2" ) )
            return 0
            ;;
    esac

    if [[ $2 == -* ]] ; then
        COMPREPLY=( $( compgen -W '--version --help --quiet --verbose --profile
            --excludes --basedir --baseurl --groupfile --checksum --pretty
            --cachedir --checkts --no-database --update --update-md-path
            --skip-stat --split --pkglist --includepkg --outputdir
            --skip-symlinks --changelog-limit --unique-md-filenames
            --simple-md-filenames --distro --content --repo --revision --deltas
            --oldpackagedirs --num-deltas --read-pkgs-list
            --max-delta-rpm-size --workers' -- "$2" ) )
    else
        COMPREPLY=( $( compgen -d -- "$2" ) )
    fi
} &&
complete -F _cr_createrepo -o filenames createrepo genpkgmetadata.py

_cr_mergerepo()
{
    COMPREPLY=()

    case $3 in
        --version|-h|--help|-a|--archlist)
            return 0
            ;;
        -r|--repo|-o|--outputdir)
            COMPREPLY=( $( compgen -d -- "$2" ) )
            return 0
            ;;
    esac

    COMPREPLY=( $( compgen -W '--version --help --repo --archlist --no-database
        --outputdir --nogroups --noupdateinfo' -- "$2" ) )
} &&
complete -F _cr_mergerepo -o filenames mergerepo mergerepo.py

_cr_modifyrepo()
{
    COMPREPLY=()

    case $3 in
        --version|-h|--help|--mdtype)
            return 0
            ;;
    esac

    if [[ $2 == -* ]] ; then
        COMPREPLY=( $( compgen -W '--version --help --mdtype' -- "$2" ) )
        return 0
    fi

    local i argnum=1
    for (( i=1; i < ${#COMP_WORDS[@]}-1; i++ )) ; do
        if [[ ${COMP_WORDS[i]} != -* &&
                    ${COMP_WORDS[i-1]} != @(=|--mdtype) ]]; then
            argnum=$(( argnum+1 ))
        fi
    done

    case $argnum in
        1)
            COMPREPLY=( $( compgen -f -o plusdirs -- "$2" ) )
            return 0
            ;;
        2)
            COMPREPLY=( $( compgen -d -- "$2" ) )
            return 0
            ;;
    esac
} &&
complete -F _cr_modifyrepo -o filenames modifyrepo modifyrepo.py

# Local variables:
# mode: shell-script
# sh-basic-offset: 4
# sh-indent-comment: t
# indent-tabs-mode: nil
# End:
# ex: ts=4 sw=4 et filetype=sh
