# L2 proposals to review

Tick `[x]` to accept. Anything left `[ ]` is rejected when this file is applied.


## click

- [x] `35b4f6f1-a8f9-4957-9f5c-71410052aba0` **Avoid ternary expressions** — Use explicit if/else blocks instead of ternary expressions because coverage cannot measure both branches of a ternary expression.  
  _evidence: docs/contributing.md:10-44_
- [ ] `1e448ced-11a4-489a-b53c-1b90beea342d` **Boolean deprecation labels** — Preserve support for `deprecated=True` when formatting deprecation labels: it must produce `(DEPRECATED)`, without an empty message suffix such as `(DEPRECATED: )`.  
  _evidence: review PR #3430 (https://github.com/pallets/click/pull/3430#discussion_r3279624975)_
- [ ] `b34333dc-fb48-45eb-959e-37685ad98e9d` **Document only the named alternative option prefixes** — In option-prefix documentation, name `/` and `+` as alternatives to `-` and acknowledge that others exist. Keep the other supported prefix characters an implementation detail rather than listing them.  
  _evidence: review PR #3192 (https://github.com/pallets/click/pull/3192#discussion_r2777100547); review PR #3192 (https://github.com/pallets/click/pull/3192#discussion_r2777030270)_
- [ ] `e7fbff7c-0df8-4745-9aab-0d31df37fb98` **Document translator comments when introducing them** — If introducing the `# TRANSLATORS:` comment convention, add documentation explaining its use.  
  _evidence: review PR #2902 (https://github.com/pallets/click/pull/2902#discussion_r3167639137)_
- [x] `047de172-54b1-4bad-a362-435588f6b41b` **Extend existing tests for individual bug fixes** — For a single bug fix, extend an existing test, preferably with another parametrization, instead of creating a new test file.  
  _evidence: review PR #3104 (https://github.com/pallets/click/pull/3104#discussion_r2411329496)_
- [x] `928c7685-878c-4709-ad96-c3e548b140ad` **Extra regression test environments** — Run `tox r -e stress` to check for race conditions in Click's test runner and `tox r -e random` to detect test pollution through parallel tests in random order. The `.github/workflows/test-flask.yaml` CI workflow runs Flask's test suite to catch downstream regressions.  
  _evidence: docs/contributing.md:10-44_
- [ ] `16c0f25e-8bd8-4222-999c-a09cac76c67b` **Flag defaults and non-boolean flag values** — Flag defaults are passed through as-is, including default=None. The special substitution of default=True with flag_value applies only to non-boolean flags; boolean flags preserve default=True even when flag_value=False.  
  _evidence: review PR #3239 (https://github.com/pallets/click/pull/3239#discussion_r3071383183); review PR #3239 (https://github.com/pallets/click/pull/3239#discussion_r3071382395)_
- [x] `7c04d2c2-b09f-48c6-ab35-116e911a13bd` **Formatting translated strings** — Use `.format()` rather than f-strings when formatting translated strings, to support gettext/PyBabel extraction.  
  _evidence: review PR #2902 (https://github.com/pallets/click/pull/2902#discussion_r3186449656)_
- [x] `b775eaca-4b41-4425-a513-f9bb5763b2a7` **Keep comments self-contained and omit issue links** — Avoid GitHub links and issue references in documentation, code comments, and test docstrings; include the relevant explanation directly. Keep implementation comments concise and place implementation details near the relevant code.  
  _evidence: review PR #3245 (https://github.com/pallets/click/pull/3245#discussion_r3058311821); review PR #3237 (https://github.com/pallets/click/pull/3237#discussion_r2869485464); review PR #3237 (https://github.com/pallets/click/pull/3237#discussion_r2869484639)_
- [x] `48d7c333-4b98-485f-a72a-d6828be68456` **Keep English confirmation responses valid** — When translating `confirm` responses, continue accepting the standard English responses alongside translated responses. In particular, both `y` and `yes` must remain valid alongside their translations.  
  _evidence: review PR #2902 (https://github.com/pallets/click/pull/2902#discussion_r3196452512); review PR #2902 (https://github.com/pallets/click/pull/2902#discussion_r3196049308)_
- [x] `188a9557-2d6a-4ba7-baf9-55ac635fab48` **Keep the default convert method concrete** — Keep `convert` in `src/click/types.py` non-abstract: supported patterns in formatting, info dictionaries, and shell completion rely on subclasses that do not override it.  
  _evidence: review PR #3371 (https://github.com/pallets/click/pull/3371#discussion_r3147795922)_
- [x] `0c750cd7-888d-406a-808e-76b73070af28` **Markdown line length** — Wrap lines in Markdown files at 80 characters.  
  _evidence: docs/contributing.md:10-44_
- [ ] `b5f54bdb-c0ff-4cd4-8af0-a7310d46b771` **Multi-command is an alias for Group** — Describe Multi-command as an alias for Group that previously had a slightly different implementation and is planned for removal in 9.0.  
  _evidence: review PR #3210 (https://github.com/pallets/click/pull/3210#discussion_r3164918721)_
- [x] `a9eebeec-c2e3-495c-b9ef-6e80baf0d568` **Prefer decorated-function terminology in documentation** — Avoid using “callback” in documentation unless necessary, since readers may not know the term. When explaining option argument-name inference, use “decorated function argument name”.  
  _evidence: review PR #3192 (https://github.com/pallets/click/pull/3192#discussion_r2767870679); review PR #3192 (https://github.com/pallets/click/pull/3192#discussion_r2767863472); review PR #3192 (https://github.com/pallets/click/pull/3192#discussion_r2750813985)_
- [x] `5f312add-d94b-4972-bf59-afff3fb2fba4` **Prefer executable documentation examples** — Prefer `click:run` for documentation examples so their output updates with the code. Static `console` blocks are acceptable while support for `click:run` in myst is unavailable.  
  _evidence: review PR #3171 (https://github.com/pallets/click/pull/3171#discussion_r2646311076)_
- [x] `a45313c2-ef66-4d17-bccc-dcef62bca8bd` **Prefer the standard library over new dependencies** — Do not add an external dependency when the feature can be implemented with the standard library.  
  _evidence: docs/contributing.md:10-44_
- [ ] `53ed2c4d-2795-48d9-93f9-763eaefc6652` **Test pager behavior through public APIs** — Test pager behavior through `get_pager_file` and `echo_via_pager` instead of monkeypatching `_pager_contextmanager`. Exercise `PAGER` settings such as `cat`, an unset value, and a missing binary.  
  _evidence: review PR #3405 (https://github.com/pallets/click/pull/3405#discussion_r3186795187); review PR #3405 (https://github.com/pallets/click/pull/3405#discussion_r3186763152)_
- [x] `52cbea0b-fd9a-4daf-9af6-ec200d6608e9` **Translate only user-facing messages** — Mark only user-facing messages for translation; leave developer-facing messages unmarked.  
  _evidence: review PR #2902 (https://github.com/pallets/click/pull/2902#discussion_r2296117331)_
- [x] `1346d41f-f50d-4333-b9ce-dcfce5400f11` **Type variable naming** — Name type variables without a leading underscore to match the repository's existing convention.  
  _evidence: review PR #3460 (https://github.com/pallets/click/pull/3460#discussion_r3289732324)_
- [ ] `b6614c45-c619-4dc6-b631-08bf77196fc4` **Use the shared Windows platform flag** — In `src/click/testing.py`, import `WIN` from `._compat` and use `if WIN:` for Windows-specific branches instead of checking `sys.platform` directly.  
  _evidence: review PR #3452 (https://github.com/pallets/click/pull/3452#discussion_r3309419417)_

## cobra

- [ ] `57111631-e3c5-4687-bd29-7783dd6a3481` **Account for both unsupported Nushell filtering directives** — In the Nushell external completer, treat both ShellCompDirectiveFilterFileExt and ShellCompDirectiveFilterDirs as unsupported when handling completion directives.  
  _evidence: review PR #1857 (https://github.com/spf13/cobra/pull/1857#discussion_r1059089976)_
- [x] `8e74fbd2-41e4-4b91-8d78-bb196d7ccf33` **Arguments passed to help functions** — Pass only the remaining arguments, after removing the subcommand and parsed flags, to HelpFunc(), matching Run/RunE. When DisableFlagParsing is true, preserve the unparsed arguments explicitly because cmd.Flags().Args() is not populated.  
  _evidence: review PR #2158 (https://github.com/spf13/cobra/pull/2158#discussion_r1634943851); review PR #2158 (https://github.com/spf13/cobra/pull/2158#discussion_r1632492757)_
- [x] `18f2b595-a319-4c6f-8555-ab09e60cb3f6` **Bash completion development targets v2** — Target new Bash completion functionality at v2; the v1 completion logic is not expected to evolve.  
  _evidence: review PR #2099 (https://github.com/spf13/cobra/pull/2099#discussion_r1521246061)_
- [ ] `8e1399de-221c-4b53-993e-dbf9f4e2c7f7` **Cobra is installed as a library dependency** — Use go get to add or update github.com/spf13/cobra as a module dependency in installation instructions. Cobra is a library, so go install is not the appropriate command.  
  _evidence: review PR #2121 (https://github.com/spf13/cobra/pull/2121#discussion_r1518713889)_
- [x] `9e012a85-5c1a-4386-8f96-2ae4edc3c3e2` **Combine Fish completion conditions for older versions** — In generated Fish completions, combine conditions with `&&` inside a single `-n` argument instead of using multiple `-n` arguments, which require Fish 3.5.  
  _evidence: review PR #1903 (https://github.com/spf13/cobra/pull/1903#discussion_r1103642664)_
- [x] `18884fd8-af93-4eb5-8251-9f7dbe99ba09` **CommandName is root-only** — Only set CommandName on the root command, and document this restriction on the field.  
  _evidence: review PR #2018 (https://github.com/spf13/cobra/pull/2018#discussion_r1299509398)_
- [ ] `198b0f3b-50cd-445e-a766-5161f5624926` **Completion environment lookup behavior and visibility** — Keep the completion environment lookup helper private because its suffix constants are private. Preserve its precedence: use a nonempty <PROGRAM>_<SUFFIX>, otherwise COBRA_<SUFFIX>, deriving <PROGRAM> from the uppercased root command name with non-ASCII-alphanumeric characters replaced by underscores.  
  _evidence: review PR #1938 (https://github.com/spf13/cobra/pull/1938#discussion_r1421574589)_
- [ ] `9e375d39-7af9-4e3f-ac8a-f779772e33f2` **Disable completion descriptions through the default completion command** — The default completion command accepts --no-descriptions to disable completion descriptions. Document this option under the existing "Descriptions for completions" section.  
  _evidence: review PR #1901 (https://github.com/spf13/cobra/pull/1901#discussion_r1090502112); review PR #1901 (https://github.com/spf13/cobra/pull/1901#discussion_r1090499987)_
- [x] `70098ded-cc56-421d-a065-9ac1d13b0a37` **Error prefix defaults and inheritance** — ErrPrefix() must default to "Error:" when no custom prefix is set. Subcommands inherit the root's error prefix unless they set their own; errors from a subcommand must use that subcommand's effective prefix.  
  _evidence: review PR #2023 (https://github.com/spf13/cobra/pull/2023#discussion_r1319266611); review PR #2023 (https://github.com/spf13/cobra/pull/2023#discussion_r1319261849); review PR #2023 (https://github.com/spf13/cobra/pull/2023#discussion_r1311425280)_
- [x] `c26f00d9-fe33-4c6a-a05f-b151aa3df289` **Exclude hidden and deprecated flags from YAML and man documentation** — Omit flags from generated YAML and man documentation when flag.Hidden is true or flag.Deprecated is nonempty.  
  _evidence: review PR #1664 (https://github.com/spf13/cobra/pull/1664#discussion_r1375485949)_
- [ ] `39bea838-c320-41eb-9f88-93b114adf296` **Hugo configuration and theme dependency** — Keep the site's Hugo configuration in hugo.yml using YAML. Import github.com/bep/docuapi/v2 through Hugo modules and omit the theme setting, which conflicts with the module setup.  
  _evidence: review PR #1984 (https://github.com/spf13/cobra/pull/1984#discussion_r1436536049); review PR #1984 (https://github.com/spf13/cobra/pull/1984#discussion_r1436527182); review PR #1984 (https://github.com/spf13/cobra/pull/1984#discussion_r1436521148)_
- [x] `7909e10a-0c13-48a6-a7cf-de4c43927970` **Keep Nushell completion setup program-independent** — Keep the Nushell completion script program-independent so users can install it once through `config nu` for all Cobra programs. Disable active help with `COBRA_ACTIVE_HELP=0` rather than a program-specific environment variable.  
  _evidence: review PR #1857 (https://github.com/spf13/cobra/pull/1857#discussion_r1045338115)_
- [x] `d9829585-23f9-46b4-8229-77b4cca9a66d` **Persistent run hook traversal is opt-in** — EnableTraverseRunHooks is disabled by default, so only the first persistent run hook found is executed. Enabling it executes persistent pre-run and post-run hooks from all parents.  
  _evidence: review PR #2044 (https://github.com/spf13/cobra/pull/2044#discussion_r1358716422)_
- [x] `ba276689-bde8-421a-bddf-ad6edf8f60b3` **PowerShell completion ordering** — PowerShell completions sort alphabetically by Name by default. Preserve the program's completion order when `ShellCompDirectiveKeepOrder` is set.  
  _evidence: review PR #1903 (https://github.com/spf13/cobra/pull/1903#discussion_r1103281594)_
- [ ] `e4d15e44-1d83-4bf7-a945-b4ad4b651d8f` **Preserve active-help environment variable naming** — Preserve activeHelpEnvVar's naming format because users rely on it explicitly. Uppercase the command name and activeHelpEnvVarSuffix, then replace every character outside A-Z, 0-9, and underscore with an underscore.  
  _evidence: review PR #1940 (https://github.com/spf13/cobra/pull/1940#discussion_r1234302153); review PR #1940 (https://github.com/spf13/cobra/pull/1940#discussion_r1234265990)_
- [x] `c9cc2a44-6dea-492f-b37d-a68226ea02d6` **Preserve Bash completion compatibility** — Keep both Bash completion implementations compatible with Bash v3 and v4/v5. Guard `compopt -o nosort` because it requires Bash 4.4, and preserve the default `nospace` registration for Bash 3, where `compopt` is unavailable.  
  _evidence: review PR #1903 (https://github.com/spf13/cobra/pull/1903#discussion_r1103644029); review PR #1903 (https://github.com/spf13/cobra/pull/1903#discussion_r1103262575); review PR #1903 (https://github.com/spf13/cobra/pull/1903#discussion_r1093707428)_
- [x] `b0343659-befc-45f0-b715-5ea3a9ac22f3` **Preserve Go 1.15 compatibility** — Cobra supports Go 1.15; keep code compatible with that version. Use interface{} instead of any, which requires Go 1.18.  
  _evidence: review PR #2085 (https://github.com/spf13/cobra/pull/2085#discussion_r1438379000)_
- [x] `47ad9158-c5a8-4262-ba25-c67a00e444e6` **Preserve the Global Flags help heading** — Keep the inherited-flags heading as "Global Flags:" in command help output; existing tools and users rely on that longstanding wording.  
  _evidence: review PR #2043 (https://github.com/spf13/cobra/pull/2043#discussion_r1382328170); review PR #2043 (https://github.com/spf13/cobra/pull/2043#discussion_r1375298111)_
- [ ] `a72f1545-d6a1-4bb5-9fe9-54cedeaebae1` **Site Hugo module identity** — Use github.com/spf13/cobra/site as the site's module path. Initialize and tidy it with `hugo mod init github.com/spf13/cobra/site` and `hugo mod tidy`.  
  _evidence: review PR #1984 (https://github.com/spf13/cobra/pull/1984#discussion_r1435720554)_
- [ ] `3c04f66d-1d71-47f3-a7b5-7a39d6e59381` **Translation extraction dependencies and CI** — Make i18n_extract depend on a target that installs github.com/leonelquinteros/gotext/cli/xgotext with go install. Run extraction in .github/test.yml and fail CI if default.pot or other generated files change.  
  _evidence: review PR #2090 (https://github.com/spf13/cobra/pull/2090#discussion_r1435309281); review PR #2090 (https://github.com/spf13/cobra/pull/2090#discussion_r1435306555)_
- [ ] `c79302d5-4f68-4f4f-a3a7-67406b92f234` **Translation keys and formatting** — Use the original English text as the key for gotext.Get() calls. Pass formatting parameters inside gotext.Get() so ordinary percent format specifiers work.  
  _evidence: review PR #2090 (https://github.com/spf13/cobra/pull/2090#discussion_r1435423475); review PR #2090 (https://github.com/spf13/cobra/pull/2090#discussion_r1435350897)_

## curl

- [x] `b943285d-8571-4c89-ab51-07eab30595b5` **bufq blocking behavior and peek lifetime** — Curl_bufq_write on a full queue and Curl_bufq_read on an empty queue return CURLE_AGAIN and set their output count to -1. Memory exposed by Curl_bufq_peek is valid only until the next operation on that bufq.  
  _evidence: docs/internals/BUFQ.md:12-63; docs/internals/BUFQ.md:65-84_
- [x] `81366045-05a3-4450-b37d-d0ac9f54b444` **bufq fullness and soft limits** — Do not infer bufq fullness from its byte length: full means it uses max_chunks and its last chunk cannot accept writes. BUFQ_OPT_SOFT_LIMIT permits writes beyond max_chunks even while reporting full, so callers must impose other checks to bound growth.  
  _evidence: docs/internals/BUFQ.md:132-159_
- [x] `5888513e-b57c-41b9-b9c4-6bac50672098` **bufq pool sharing** — Share a struct bufc_pool between bufqs only when they all operate in the same thread, as transfers using the same multi handle do. The pool manages chunk sizes and retains spare chunks for reuse across its bufqs.  
  _evidence: docs/internals/BUFQ.md:160-184_
- [x] `7d722c8c-0a92-4c67-b65a-44c6f390ac0b` **bufref API and initialization** — Access and modify struct bufref members only through the dedicated bufref API, and call Curl_bufref_init before any other operation. Use Curl_bufref_free to destroy the referenced buffer through its destructor and reinitialize the structure for reuse.  
  _evidence: docs/internals/BUFREF.md:7-20; docs/internals/BUFREF.md:21-43_
- [x] `25d7a203-abb0-4b79-ac2a-196ff279f5f1` **bufref buffer ownership constraints** — Do not reallocate a buffer while it is referenced by a bufref. Curl_bufref_set releases the previous buffer and associates the replacement with its destructor; a static buffer may use a NULL destructor, and a NULL buffer requires zero length.  
  _evidence: docs/internals/BUFREF.md:7-20; docs/internals/BUFREF.md:44-56_
- [x] `65ab87f5-f212-40ce-a321-4ccc8980be3f` **C control-flow formatting** — Put opening braces for if/while/do/for on the keyword line without a space before the parenthesis, closing braces at the keyword's indentation, and else on a new line; function opening braces go on a separate line. Braces may be omitted for a single one-line statement, but keep statements on separate lines and move assignments outside if/while conditions.  
  _evidence: docs/internals/CODE_STYLE.md:85-137; docs/internals/CODE_STYLE.md:152-188_
- [x] `046d6419-6b25-4a0e-b495-89722df5e915` **C indentation, comments and local functions** — In C code, indent with two spaces per brace level and never use tabs; use /* comments */ because curl targets C89 and disallows // comments. Make file-local functions static and prefer lowercase names.  
  _evidence: docs/internals/CODE_STYLE.md:38-70_
- [x] `03d9149c-2177-4052-9ff6-3f0fe1c2d325` **Client reader phase ordering** — Client readers are ordered by phase: CURL_CR_NET, CURL_CR_TRANSFER_ENCODE, CURL_CR_PROTOCOL, CURL_CR_CONTENT_ENCODE, then CURL_CR_CLIENT. A newly added reader precedes existing readers in the same phase, so choose its phase with data transformation order in mind.  
  _evidence: docs/internals/CLIENT-READERS.md:74-95_
- [x] `98687854-3ee2-485a-a347-b28df549f72b` **Client reader resume semantics** — Upload resumption applies to the CURL_CR_CLIENT reader and reduces its reported total length by the resumed offset; unsupported resumption or an excessive offset can fail. Repeated resume_from() calls are additive and cannot currently be undone.  
  _evidence: docs/internals/CLIENT-READERS.md:156-168_
- [x] `5871d6cf-b135-4404-b409-a00c060c233f` **Client writer ordering and decoding boundaries** — Client writers run in phase order CURL_CW_RAW, CURL_CW_TRANSFER_DECODE, CURL_CW_PROTOCOL, CURL_CW_CONTENT_DECODE, then CURL_CW_CLIENT; a newly added writer precedes existing writers in its phase. Perform response length checks in CURL_CW_PROTOCOL, after transfer decoding and before content decoding, because Content-Length applies to the content before content decoding.  
  _evidence: docs/internals/CLIENT-WRITERS.md:83-122; docs/internals/CLIENT-WRITERS.md:123-158_
- [x] `cc22b8b9-688d-4ae9-80ca-5e032589673f` **Connection encryption follows filter flag order** — Determine connection encryption by inspecting the filter chain from the top: CF_TYPE_SSL means encrypted, but encountering CF_TYPE_IP_CONNECT first means unencrypted. When a filter has both flags, check CF_TYPE_SSL first.  
  _evidence: docs/internals/CONNECTION-FILTERS.md:182-222_
- [x] `f1717694-c923-49a4-808d-f0255e70e046` **Connection filter connect and close ordering** — A connection filter must let downstream filters finish connecting before performing its own connection work, propagating errors or incomplete status. When closing, perform the filter's own cleanup before asking the next filter to close.  
  _evidence: docs/internals/CONNECTION-FILTERS.md:67-103_
- [x] `dca65240-79d5-48f7-93d1-f12b7713dd97` **Connection filter tracing** — Use CURL_TRC_CF(data, cf, msg, ...) for connection filter diagnostics. Enable these traces with case-insensitive filter type names or all in --trace-config, or with curl_global_trace(config_string) at application startup.  
  _evidence: docs/internals/CONNECTION-FILTERS.md:254-274_
- [x] `3f617a9e-0b2f-4695-a4a7-03ddef238fff` **Connection filter type and instance state** — Keep each connection filter's cft as a singleton static struct for its type, and store filter-specific instance state in ctx. Allocate that state when needed and release it when its purpose ends.  
  _evidence: docs/internals/CONNECTION-FILTERS.md:104-148_
- [x] `47025d36-2ea2-482c-9abe-7fc4ce65e3c1` **Contribution licensing and copyright** — Contribute code under curl and libcurl's existing license unless otherwise agreed; a larger separate component may use another GPL-compatible license, but cannot itself be GPL licensed or impose changes on the rest of the package. Preserve the original copyright ownership when modifying existing source files.  
  _evidence: docs/CONTRIBUTE.md:30-52_
- [x] `3c9989d4-6b5f-4810-9f4e-69e3aa64f1dd` **Delegate connection filter output downstream** — Connection filters must send their processed data through the next filter rather than assume a particular downstream transport. The next filter may represent a socket, file, or HTTP/2 connection.  
  _evidence: docs/internals/CONNECTION-FILTERS.md:13-49_
- [x] `dcee084b-421e-4e28-a62c-1446b14c0fa2` **Do not typedef structs** — Refer to structures using struct name; do not introduce typedefs for structs.  
  _evidence: docs/internals/CODE_STYLE.md:314-336_
- [x] `826d1475-26a2-42cf-a516-7655316529ea` **Documentation source formats** — Man pages are rendered from source files usually written in Markdown, and most HTML files on the website and in release archives are generated from corresponding Markdown and ASCII files. Make documentation changes in the corresponding source files.  
  _evidence: docs/CONTRIBUTE.md:107-118_
- [x] `70c4c27f-1366-484e-9dfa-3d92381e5e44` **Feature-based platform conditionals** — Use #ifdef HAVE_FEATURE rather than operating-system or hardware checks; feature definitions come from configure on Unix-like systems and config-[system].h elsewhere. Prefer macros or functions that become empty or constant when a feature is disabled so callers need fewer conditionals.  
  _evidence: docs/internals/CODE_STYLE.md:289-313_
- [ ] `bffb02bd-9a0e-4939-9f82-925745075cfc` **Feature-window merge restriction** — Merge pull requests for new features or changes only while the feature window is open, typically for three weeks starting ten days after the previous release. Submissions made while the window is closed must wait for it to open before merging.  
  _evidence: docs/CONTRIBUTE.md:188-203_
- [x] `25698e66-dae7-40e6-91e4-3abb1299fcf1` **Integrate related coverage into existing tests** — Prefer adding related coverage to an existing test in tests/data, tests/libtest, or tests/unit before introducing another standalone test. Consolidate closely related cases and weigh a separate test's repeated execution cost against the importance of the case.  
  _evidence: review PR #23526 (https://github.com/curl/curl/pull/23526#discussion_r4337292596); review PR #23499 (https://github.com/curl/curl/pull/23499#discussion_r4337212567); review PR #23500 (https://github.com/curl/curl/pull/23500#discussion_r4337193987); review PR #23536 (https://github.com/curl/curl/pull/23536#discussion_r4336704162); review PR #23501 (https://github.com/curl/curl/pull/23501#discussion_r4323511463); review PR #23487 (https://github.com/curl/curl/pull/23487#discussion_r4312711638); review PR #23472 (https://github.com/curl/curl/pull/23472#discussion_r4306808013)_
- [x] `438eb772-3257-44e8-afa0-38578b1eeb5d` **List test cases one per line** — Keep each TESTCASES entry on its own line in tests/data/Makefile.am.  
  _evidence: review PR #23460 (https://github.com/curl/curl/pull/23460#discussion_r4304775607)_
- [ ] `958bdc79-db8a-4e33-91f2-48340a04f750` **Port retrieval does not URL-decode** — Pass 0 for the flags when retrieving CURLUPART_PORT with curl_url_get(); CURLU_URLDECODE has no effect on port numbers.  
  _evidence: review PR #23454 (https://github.com/curl/curl/pull/23454#discussion_r4306614469)_
- [x] `f252ac8e-479c-46c5-9985-54c8adacec10` **Prefer inline checksrc suppressions** — Suppress checksrc warnings with inline ignores wherever possible instead of checksrc.skip files. Use a counted suppression such as /* !checksrc! disable LONGLINE 1 */ for specific occurrences, or pair a disable with an enable for a section; inline suppressions apply only to their source file.  
  _evidence: docs/internals/CHECKSRC.md:159-195_
- [x] `ab2345d5-bd90-4754-80b7-7326a56f7402` **Reader replacement and rewind on retries** — Request retries discard installed client readers and create replacements that must upload the same data, so callback readers must rewind their underlying content when needed. Use Curl_creader_needs_rewind(data) to check necessity, Curl_creader_set_rewind(data, TRUE) to schedule rewinding, and Curl_client_start(data) to perform the requested rewind at the next request's start.  
  _evidence: docs/internals/CLIENT-READERS.md:169-189_
- [ ] `1176ff0c-3602-4249-ab39-453125858123` **Reports of AI-discovered issues** — When reporting an issue discovered using AI, disclose that use and independently verify that the issue exists and behaves as claimed. Write the report yourself from the verified findings instead of copying an AI-generated report.  
  _evidence: docs/CONTRIBUTE.md:315-339_
- [x] `62978af3-2e8b-4449-a5ae-bb3f7e174276` **Required C helper substitutions** — Use curl_msnprintf() instead of snprintf(), and use mode-string macros with curlx_fopen() and curlx_freopen(). Replace curlx_free(var) immediately followed by assigning NULL to var with curlx_safefree().  
  _evidence: docs/internals/CHECKSRC.md:73-125; docs/internals/CHECKSRC.md:127-135_
- [x] `fb1bf08d-5e1f-422a-96bd-66555e9b9bad` **Respect the banned C function list** — Avoid the functions listed under Banned functions in docs/internals/CODE_STYLE.md; checksrc enforces this repository-specific ban.  
  _evidence: docs/internals/CODE_STYLE.md:337-437_
- [x] `f920ffd4-a7ef-4279-b1e8-0de922671198` **REUSE compliance for all files** — Give every file explicit copyright and license information, preferably using the standard curl header with SPDX-License-Identifier; use a smaller header or REUSE.toml when needed. Run reuse lint to check compliance with the REUSE compliance / check CI job.  
  _evidence: docs/CONTRIBUTE.md:296-314_
- [x] `022ce18b-113b-4108-bed0-dcf8932567ee` **Route response data through client writers** — Forward libcurl response data to the application through Curl_client_write() so the common writer chain applies. Keep CLIENTWRITE_BODY and CLIENTWRITE_HEADER mutually exclusive; use the header modifier bits to describe the header's purpose.  
  _evidence: docs/internals/CLIENT-WRITERS.md:26-44; docs/internals/CLIENT-WRITERS.md:45-82; docs/internals/CLIENT-WRITERS.md:159-168_
- [ ] `4d3556be-5be4-4041-9e96-03cc3ff62e0d` **Schannel limitations on older Windows** — Keep docs/INSTALL.md and docs/SSL-PROBLEMS.md consistent in identifying Windows 8 and earlier for the legacy Schannel warning. Schannel capabilities depend on the Windows version; recommend another SSL backend when required handshakes or algorithms are unavailable.  
  _evidence: review PR #23455 (https://github.com/curl/curl/pull/23455#discussion_r4304602788); review PR #23455 (https://github.com/curl/curl/pull/23455#discussion_r4304571197)_
- [x] `10297861-b1cb-4eb4-8ce4-fac6406264fc` **Test coverage for new functionality** — Cover all new features and functions in the test suite, with at least one valid test case per new feature verifying its documented behavior. If test cases are absent or difficult to write, explain exactly how the changes were otherwise tested and verified.  
  _evidence: docs/CONTRIBUTE.md:119-133_
- [ ] `c186ddec-3094-4948-b49a-7cd7a3395961` **Test linter duplicate-tag exceptions** — Duplicate-tag validation in tests/test-linter.pl allows certain tags to occur twice. Preserve the maximum of two occurrences for those exceptions when changing the validation.  
  _evidence: review PR #23573 (https://github.com/curl/curl/pull/23573#discussion_r4357677047); review PR #23573 (https://github.com/curl/curl/pull/23573#discussion_r4357358642)_
- [x] `5777cb88-8940-453a-b009-718a35e7b52d` **Transformed and raw upload lengths** — Use Curl_creader_total_length(data) for the upload length after reader transformations; unknown lengths return -1, including line-end conversion of positive raw content lengths. Curl_creader_client_length(data) reports the raw length from CURL_CR_CLIENT without consulting transforming readers.  
  _evidence: docs/internals/CLIENT-READERS.md:133-155_

## requests

- [x] `f17e10b9-2671-45d4-b860-bc107d002d99` **Avoid the legacy Unicode helper in tests** — Do not use the u helper from tests/compat.py in repository tests; the reviewer explicitly requested removing all test usages despite retaining its definition for possible external users.  
  _evidence: review PR #6091 (https://github.com/psf/requests/pull/6091#discussion_r833422816)_
- [ ] `04b5377b-29b1-4049-b562-6cb98fdcadcc` **Bug report preparation** — Before filing a bug report, check both open and closed GitHub issues for duplicates. Include expected and actual results, reproduction steps, and system information from python -m requests.help; for Requests versions before v2.16.4, provide basic system details instead.  
  _evidence: docs/dev/contributing.rst:141-151; .github/ISSUE_TEMPLATE.md:1-28_
- [x] `f1c50dbd-cbf8-48c6-b255-6b031fb3dbaf` **CA bundle environment variable precedence** — REQUESTS_CA_BUNDLE takes precedence over CURL_CA_BUNDLE, which serves as its fallback. Preserve this distinction when documenting CA bundle configuration.  
  _evidence: review PR #5509 (https://github.com/psf/requests/pull/5509#discussion_r457860411)_
- [ ] `a5421aaa-396d-4df8-bc41-8751f0c6708d` **Cache the default Accept-Encoding value** — In requests/utils.py, generate the default Accept-Encoding header once and reuse it in default_headers. Its value is determined by imports, so avoid calling make_headers on every invocation.  
  _evidence: review PR #5783 (https://github.com/psf/requests/pull/5783#discussion_r636462152)_
- [ ] `80e4f6cb-6bf5-4bfd-8d0e-3b07effca39f` **Code contribution validation and PR target** — For code contributions, first confirm the existing tests pass, then add tests demonstrating the bug or feature and verify they fail before implementing the change. Run the entire test suite afterward and submit the pull request against main.  
  _evidence: docs/dev/contributing.rst:65-84_
- [x] `8291a4c7-b7f3-4b19-bc8d-df19e60b3e9b` **Dependency version range syntax** — In setup.cfg, express dependency version ranges with explicit lower and upper bounds, such as >=2,<3, rather than the compatible-release operator ~=, consistent with the other dependencies.  
  _evidence: review PR #6169 (https://github.com/psf/requests/pull/6169#discussion_r906202931)_
- [x] `880457d3-9268-45a3-a527-d32d0df0b063` **Documentation format and style** — Write documentation in docs/ using reStructuredText for Sphinx, with a soft line limit of 79 characters and semi-formal, friendly prose. Use single-quoted strings in Python examples.  
  _evidence: docs/dev/contributing.rst:120-140_
- [x] `c757e10b-f63c-4b65-863b-9dbdc17b7506` **Feature freeze** — Requests is in a perpetual feature freeze; only the BDFL can add or approve new features.  
  _evidence: docs/dev/contributing.rst:152-165_
- [ ] `92660a42-962a-4901-8e9e-b87e35491261` **Distinguish default netrc filenames from custom NETRC paths** — In requests/utils.py, apply home-directory formatting only to entries from NETRC_FILES. Use custom NETRC paths without prepending the user's home directory.  
  _evidence: review PR #5643 (https://github.com/psf/requests/pull/5643#discussion_r515570061)_
- [x] `c4143ae9-6d5a-4d48-b8aa-1603c36b3ecb` **Preserve Session proxy authentication compatibility** — Preserve the behavior of rebuild_proxies and rebuild_auth because users subclass Session, including existing proxy authentication flows. Proxy-Authorization stripping must behave consistently whether or not proxies is explicitly supplied.  
  _evidence: review PR #5924 (https://github.com/psf/requests/pull/5924#discussion_r701276964); review PR #5893 (https://github.com/psf/requests/pull/5893#discussion_r692463139); review PR #5893 (https://github.com/psf/requests/pull/5893#discussion_r687392966)_
- [x] `0b31d9a1-2299-4025-9980-4d5b68eddf77` **Preserve the license metadata compatibility choice** — Keep the pyproject.toml license declaration as license = {text = "Apache-2.0"} until the project revisits PEP 639 adoption; this choice intentionally avoids requiring setuptools 77.  
  _evidence: review PR #7012 (https://github.com/psf/requests/pull/7012#discussion_r2748329758)_
- [x] `ac8a01e3-5290-4cea-bf0b-fd0fab818018` **Preserve URL parsing compatibility fallback** — In requests/utils.py, preserve the netloc/path swap as a backward-compatibility fallback when parsing yields no netloc. The known parsing quirk is associated with urlparse.  
  _evidence: review PR #5917 (https://github.com/psf/requests/pull/5917#discussion_r763565145)_
- [ ] `d1e487b5-8393-4fe6-a04f-4feb14431a55` **Private vulnerability disclosure** — Report potential security vulnerabilities through a draft GitHub Security Advisory, including the discovery code and the shortest reproduction. Keep the vulnerability private while verification and next steps are coordinated there.  
  _evidence: .github/SECURITY.md:1-30_
- [x] `2bcb9b3c-e2ff-4229-b0d8-e57a2ff5937b` **Proxy environment lookup controls** — Preserve explicit proxies and disabling trust_env as escape hatches from expensive environment proxy resolution. Only call should_bypass_proxies when trust_env is enabled.  
  _evidence: review PR #5924 (https://github.com/psf/requests/pull/5924#discussion_r701278739); review PR #5893 (https://github.com/psf/requests/pull/5893#discussion_r700780736); review PR #5894 (https://github.com/psf/requests/pull/5894#discussion_r687377459)_
- [ ] `ea948ebd-c6c2-4ed2-acd9-eab5894e6483` **Proxy scheme matching** — Requests supports multiple socks* proxy schemes, so preserve prefix matching for SOCKS schemes. Match the HTTPS proxy scheme exactly against https.  
  _evidence: review PR #5665 (https://github.com/psf/requests/pull/5665#discussion_r667219524)_
- [x] `bc6f3af3-06f0-451d-b3c4-871a624565ff` **Reuse the resolved JSON decoding exception** — Reuse JSONDecodeError from compat rather than resolving the active JSON exception again in exceptions.py. Define the Requests JSONDecodeError with InvalidJSONError and the imported CompatJSONDecodeError as parents.  
  _evidence: review PR #5856 (https://github.com/psf/requests/pull/5856#discussion_r673356731); review PR #5856 (https://github.com/psf/requests/pull/5856#discussion_r671444604)_
- [x] `ba57bfcd-74d3-4a57-8cdb-bef9945929be` **TLS verification path and CA bundle handling** — In src/requests/adapters.py, distinguish directory paths from certificate files when verify is a string instead of treating every string as ca_certs. When verify is True and the default SSLContext is bypassed, preserve the default CA bundle configuration through pool_kwargs in _urllib3_request_context.  
  _evidence: review PR #6767 (https://github.com/psf/requests/pull/6767#discussion_r1683276287); review PR #6731 (https://github.com/psf/requests/pull/6731#discussion_r1622893724)_
- [ ] `69b13525-ee98-4e62-82ea-737595cdc34f` **Unsupported Python installation guidance** — In setup.py's unsupported-Python message, direct users to upgrade Python or pin Requests to an older supported version. Omit pip/setuptools upgrade instructions and pip version recommendations.  
  _evidence: review PR #6091 (https://github.com/psf/requests/pull/6091#discussion_r834679845); review PR #6091 (https://github.com/psf/requests/pull/6091#discussion_r834612265)_
- [x] `055b4857-8d4f-4f26-8d5d-0d5681924f95` **urllib3 major-version compatibility checks** — In src/requests/compat.py, distinguish urllib3 1.x explicitly so newer major versions can follow the non-1.x behavior without being mislabeled as 2.x.  
  _evidence: review PR #6757 (https://github.com/psf/requests/pull/6757#discussion_r1695374605)_
