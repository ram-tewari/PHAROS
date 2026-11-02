# L2 proposals to review

Tick `[x]` to accept. Anything left `[ ]` is rejected when this file is applied.


## attrs

- [x] `30111ba2-83f2-48ae-81cd-7758d18debfc` **API documentation registration and version directives** — Manually add new functions/classes and signature changes to `@attr.s()` and `@attrs.define()` to `docs/api.rst`. Give changed or added classes, methods, and functions appropriate `versionadded`, `versionchanged`, or `deprecated` directives; changes affecting both `attrs.define()` and `attr.s()` require directives on both.  
  _evidence: .github/PULL_REQUEST_TEMPLATE.md:6-37_
- [ ] `142f191a-386c-425f-b8a9-8747f30ce901` **Boolean references in API docstrings** — Use Sphinx roles :data:`True` and :data:`False` when referring to boolean literals in API docstrings.  
  _evidence: review PR #1432 (https://github.com/python-attrs/attrs/pull/1432#discussion_r2099234815)_
- [ ] `e8ee3efb-37a5-41eb-98cd-59baf1ebb20e` **Canonical Python version** — The root `.python-version` file is the canonical source for the project's default Python version, including for setup-python. Use its version when creating a development virtual environment.  
  _evidence: review PR #1140 (https://github.com/python-attrs/attrs/pull/1140#discussion_r1227144596); review PR #1140 (https://github.com/python-attrs/attrs/pull/1140#discussion_r1217192780)_
- [x] `8b8974a2-567a-48cd-944a-d5a14498781c` **Docstring summary mood and return section** — Write docstring summary lines in imperative mood; the rest of the docstring explains behavior and need not use imperative mood. Label the return-value section `Returns:`.  
  _evidence: review PR #1308 (https://github.com/python-attrs/attrs/pull/1308#discussion_r1684824354)_
- [x] `3b944304-6d76-44de-b000-e3b923c7b160` **Multiline docstring layout** — In `src/attr/_make.py`, put opening and closing docstring quotes on separate lines, even for a one-sentence docstring.  
  _evidence: review PR #1407 (https://github.com/python-attrs/attrs/pull/1407#discussion_r1950385264)_
- [x] `41ef96ab-79c8-4a2c-8388-ac4c2f1aca6d` **Namedtuple serialization with retained collection types** — attr.asdict supports namedtuple fields when retain_collection_types=True, preserving their namedtuple type.  
  _evidence: review PR #1165 (https://github.com/python-attrs/attrs/pull/1165#discussion_r1277719808); review PR #1165 (https://github.com/python-attrs/attrs/pull/1165#discussion_r1277714816)_
- [x] `046ebd30-49b1-4830-b560-195a86f3fd8b` **Preserve legacy attr.ib references in documentation** — When documenting attrs.field, retain references to attr.ib where they help readers navigate older attrs code; attrs.field may appear first. Do not refer to attrs.ib, which does not exist.  
  _evidence: review PR #1163 (https://github.com/python-attrs/attrs/pull/1163#discussion_r1294287195)_
- [x] `525f55ed-03fc-4a8d-a90c-757c68a571d1` **Public API compatibility policy** — Announce compatibility breaks in the changelog and, where possible, issue a `DeprecationWarning` for a year before breaking compatibility. The structure of `attrs.Attribute` is exempt from this guarantee and should be treated as read-only.  
  _evidence: .github/SECURITY.md:3-21_
- [x] `d2d741c2-f06d-443a-b304-cdbca8d5cfd1` **Public API stubs and feature examples** — Update the `.pyi` type stubs whenever public APIs are added or changed. Demonstrate new features in `docs/examples.md`.  
  _evidence: .github/CONTRIBUTING.md:114-123; .github/CONTRIBUTING.md:142-196_
- [x] `165ac9dc-3003-48e1-9211-c477cb9eaf43` **Required tests, documentation, and coverage** — Always include tests and documentation for code changes; CI requires 100% coverage. Use `# pragma: no cover` only when maintainers agree to an exception.  
  _evidence: .github/CONTRIBUTING.md:16-47_
- [x] `8af04116-550c-49b1-bc91-e0fc2eaa9734` **Semantic newlines in documentation** — Write `.rst` and `.md` documentation using semantic newlines, with one sentence per line.  
  _evidence: .github/PULL_REQUEST_TEMPLATE.md:6-37_
- [x] `1b3340f0-ad0f-49b5-8359-522731a628d0` **Test assertions and feature strategies** — Write assertions as `expected == actual`, with an empty line before the assertion block, and give tests descriptive docstrings. Add new features to the Hypothesis testing strategy in `tests/strategies.py`.  
  _evidence: .github/CONTRIBUTING.md:124-141_
- [ ] `055b0b92-c6ca-414a-a875-55b5dbe5751c` **Towncrier changelog fragments and symbol formatting** — For user-facing changes, add a Markdown fragment under changelog.d named pr#.(change|deprecation|breaking).md, using semantic newlines and simple past tense or constructions with “now”. Format fully qualified symbols in plain backticks; Sphinx roles such as {func} do not work in changelog fragments.  
  _evidence: review PR #1068 (https://github.com/python-attrs/attrs/pull/1068#discussion_r1166499406); review PR #1068 (https://github.com/python-attrs/attrs/pull/1068#discussion_r1166459782); review PR #1068 (https://github.com/python-attrs/attrs/pull/1068#discussion_r1166290010)_
- [ ] `d0cd3a6e-4dd8-43e1-9e1e-b06070ed210b` **Type stub notation and import suggestions** — Use modern type notation in type stubs and preserve their organization so VS Code's quick-fix import suggestions prefer the attrs namespace.  
  _evidence: review PR #1234 (https://github.com/python-attrs/attrs/pull/1234#discussion_r1476999444)_

## echo

- [x] `74c95e0a-286f-4465-abc5-dbf50295c8b9` **Context parameter ordering in middleware** — When adding echo.Context to function types or fields, make it the first parameter for consistent signatures.  
  _evidence: middleware/DEVELOPMENT.md:3-11_
- [x] `6d2fdd96-aec5-412e-b867-a093a89668de` **Middleware configuration and error handling** — Do not panic on invalid configuration in middleware creator functions; provide configuration structs implementing MiddlewareConfigurator so callers can choose panic-based or error-returning creation. Request-handling middleware should return errors rather than call c.Error() and return no error, so upstream middleware can handle returned errors.  
  _evidence: middleware/DEVELOPMENT.md:3-11_

## libuv

- [x] `46e3fcfb-a02e-4985-b3eb-10450c715c63` **C source formatting and syntax** — Use two-space indentation without tabs, wrap lines at 80 characters, and use LF endings without trailing whitespace. Use C89-compliant syntax, declaring variables only at the top of a scope.  
  _evidence: CONTRIBUTING.md:44-86_
- [x] `ab039d93-6595-4b08-8bf7-0db4d2dd61fb` **Cached process IDs can identify a different process** — Calling uv_kill with a cached value of uv_process_get_pid can kill a different process that reused the PID after the original process exited. Do not rely on that combination to target only the original process.  
  _evidence: review PR #3539 (https://github.com/libuv/libuv/pull/3539#discussion_r2945078431)_
- [x] `6088a669-48b2-4db0-9a7b-095838aaaad1` **Cancellation success promises future completion** — Returning zero from uv_cancel means the request will complete in the future, allowing the caller to determine when its memory can be released. If a closing handle prevents that completion, return UV_EBUSY or another error instead.  
  _evidence: review PR #5206 (https://github.com/libuv/libuv/pull/5206#discussion_r3646095378)_
- [ ] `f0e00272-1522-41ec-b8b2-0244e8f130da` **Close process handles even when spawning fails** — After a process-spawning call succeeds or fails, call uv_close on the process handle before freeing its memory.  
  _evidence: review PR #3539 (https://github.com/libuv/libuv/pull/3539#discussion_r2945029271)_
- [x] `8247da33-c296-4f8d-826d-7e9894547f5f` **Closing handles does not impose ordering** — Do not rely on uv_close to impose an ordering between handle closures, including on Windows.  
  _evidence: review PR #4976 (https://github.com/libuv/libuv/pull/4976#discussion_r3609113435)_
- [x] `dfce4f5c-1f54-43c1-bfb6-d8fa85c30ab7` **Constant-time queue concatenation** — Use uv__queue_add to append an entire queue to another queue in O(1), avoiding an O(n) loop that removes and reinserts each entry.  
  _evidence: review PR #5189 (https://github.com/libuv/libuv/pull/5189#discussion_r3567176792)_
- [ ] `c38e21b2-7657-477b-9273-0871aff43f42` **Dedicated async handle tracking** — src/unix/async.c maintains a dedicated loop->async_handles queue to avoid scanning unrelated handles. Use dedicated async-handle tracking for similar traversal in src/win/async.c, where scanning all handles can be slow.  
  _evidence: review PR #5079 (https://github.com/libuv/libuv/pull/5079#discussion_r3236423401)_
- [ ] `95769fd0-2bbd-4ac9-85fd-ab0e6ec0d3ce` **Filesystem polling paths are dynamically allocated** — uv_fs_poll_start dynamically allocates its path storage. Do not impose a UV__PATH_MAX limit on that path.  
  _evidence: review PR #5126 (https://github.com/libuv/libuv/pull/5126#discussion_r3098247200)_
- [x] `f7efc9ed-137c-4723-a7c6-37b63533bedd` **Group Windows-only test declarations** — Place Windows-only test declarations in the existing Windows-only tests section of test/test-list.h.  
  _evidence: review PR #5148 (https://github.com/libuv/libuv/pull/5148#discussion_r3320437196)_
- [x] `8a91a616-70ef-419d-81cd-3c50bdd4be2b` **Let the test harness handle timeouts** — Rely on the test harness for test timeouts instead of adding timeout timers within tests, so timeouts do not interfere with debugging.  
  _evidence: review PR #5013 (https://github.com/libuv/libuv/pull/5013#discussion_r2955184278)_
- [ ] `ac3a588b-f20d-4f8d-b634-ac7b8ea8a4db` **Platform-dependent IPv6 address buffer size** — Use INET6_ADDRSTRLEN for the address buffer in uv_ip6_addr. POSIX requires 46 bytes including the NUL byte; Windows requires 65 bytes to accommodate optional formatting marks.  
  _evidence: review PR #5135 (https://github.com/libuv/libuv/pull/5135#discussion_r3243682116)_
- [x] `72a87897-ad4c-4b3d-ab1a-577d6bdf06e0` **Prefer features supported across platforms** — Generally avoid adding features supported on only a single platform; libuv usually does not support such features.  
  _evidence: review PR #5116 (https://github.com/libuv/libuv/pull/5116#discussion_r3240686919)_
- [x] `1c848305-3e94-4df9-91e0-4d1fe73bc026` **Prefer tests that run across platforms** — Prefer tests that run on all platforms over platform-only variants, because platform-only tests allow behavior to diverge.  
  _evidence: review PR #5013 (https://github.com/libuv/libuv/pull/5013#discussion_r2955207992)_
- [x] `5f63bf79-f188-449e-b268-8cd8eb8dcab9` **Prefer uv_open_osfhandle** — Use uv_open_osfhandle instead of _open_osfhandle when converting Windows OS handles to file descriptors, including in tests.  
  _evidence: review PR #5148 (https://github.com/libuv/libuv/pull/5148#discussion_r3320456195)_
- [x] `6450ab84-11cc-432a-bceb-170de34954c8` **Prefix internal fallback macros with UV__** — Prefix fallback macro definitions in src/unix/internal.h with UV__, including the KEVENT_FLAG_IMMEDIATE and KEVENT_FLAG_NONE fallbacks, to avoid name conflicts.  
  _evidence: review PR #5043 (https://github.com/libuv/libuv/pull/5043#discussion_r2943952808); review PR #5043 (https://github.com/libuv/libuv/pull/5043#discussion_r2930511609)_
- [ ] `bb4aaf31-6349-4773-8603-ca08c4775206` **Preserve the Windows global job object during cleanup** — Leave the global job object open when cleaning up libuv on Windows. Closing it terminates every process still assigned to it, which should happen when the process exits rather than when it stops using libuv.  
  _evidence: review PR #5214 (https://github.com/libuv/libuv/pull/5214#discussion_r3678039423)_
- [x] `ec93a0d1-ebf5-41c5-92b5-8af996a283ea` **Reserve handle data for applications** — Do not use a handle's public data pointer to store libuv internal state; it is reserved for application use.  
  _evidence: review PR #5127 (https://github.com/libuv/libuv/pull/5127#discussion_r3098376612)_
- [ ] `92b68dd3-0c87-4dc5-aecc-7ea9e4f0c4d1` **Shared I/O transfer limit** — Use UV__IO_MAX_BYTES (0x7ffff000) as the shared limit for read and write transfers to avoid platform-specific failures with large requests.  
  _evidence: review PR #5076 (https://github.com/libuv/libuv/pull/5076#discussion_r2956447323)_
- [x] `f23c2e69-7f90-4b5a-81d4-c29dd535b23b` **Thread pool request classification** — Do not use a NULL work callback to identify requests outside the thread pool: worker() clears req->work concurrently when processing finishes. Use the done callback for this distinction because it is never modified and is never NULL for requests that go through the thread pool.  
  _evidence: review PR #5229 (https://github.com/libuv/libuv/pull/5229#discussion_r3792768598)_
- [ ] `3d0cf13b-ad01-4130-b13a-17d81d402f2b` **Use the completed Windows pipe I/O result** — Determine Windows pipe I/O success from the I/O operation's result rather than the result of CancelIoEx. An ERROR_OPERATION_ABORTED result with bytes > 0 indicates that data was successfully transferred.  
  _evidence: review PR #5115 (https://github.com/libuv/libuv/pull/5115#discussion_r3067997630); review PR #4966 (https://github.com/libuv/libuv/pull/4966#discussion_r3065201090)_
- [ ] `06465dd7-9ae4-4851-9ad0-202a449408e9` **Verify async handle ABI after private-field changes** — When changing UV_ASYNC_PRIVATE_FIELDS in include/uv/win.h, manually verify that sizeof(uv_async_t) remains unchanged.  
  _evidence: review PR #5079 (https://github.com/libuv/libuv/pull/5079#discussion_r3236391364)_
- [ ] `45d4d1b9-131d-4fd0-99e1-10e7f0df714f` **Windows pipe IOCP completion requirements** — Windows pipe servers require IOCP to avoid deadlock. Do not enqueue requests in pending_reqs when they will complete via IOCP.  
  _evidence: review PR #5071 (https://github.com/libuv/libuv/pull/5071#discussion_r2946150690); review PR #5071 (https://github.com/libuv/libuv/pull/5071#discussion_r2946147191)_

## rich

- [x] `9ed90979-3d03-4212-a37d-3f4b77ca7f19` **Accept style strings and Style objects** — Use StyleType for style parameters so callers can pass either a string such as "bold red" or a Style object. When a Style object is needed, resolve the value with console.get_style(style_type).  
  _evidence: review PR #2341 (https://github.com/Textualize/rich/pull/2341#discussion_r901368761)_
- [x] `4861de9a-a8ce-4081-bc51-d4e04f60d40b` **Avoid abbreviated names** — Rich has a strict policy against abbreviations in names; use descriptive names instead of names such as `x` or `s`.  
  _evidence: review PR #2905 (https://github.com/Textualize/rich/pull/2905#discussion_r1150405311)_
- [ ] `416ef850-8fc5-4393-91e2-c0aa220b614d` **Completed progress has zero remaining time** — When a progress task has zero remaining work, its remaining-time estimate should return 0 rather than None.  
  _evidence: review PR #2166 (https://github.com/Textualize/rich/pull/2166#discussion_r843921537)_
- [x] `cc33702d-0456-4889-9f4d-b8b2e671a454` **Console context blocks buffer output atomically** — The `with console:` context buffers all content until the block exits, making its output atomic. Preserve this behavior when changing buffering or its interaction with `console.capture()`.  
  _evidence: review PR #2347 (https://github.com/Textualize/rich/pull/2347#discussion_r908476507)_
- [x] `99bfee3b-543b-49c7-873d-b553e92d7c72` **Demo content affects tests and screenshots** — The example content in rich/__main__.py is used by tests and screenshots. When changing that content, account for affected tests and regenerate the screenshots.  
  _evidence: review PR #1862 (https://github.com/Textualize/rich/pull/1862#discussion_r793485978)_
- [ ] `3fdaee78-2845-4ad3-bccd-b00bf42be358` **Document parameters of private Windows console wrappers** — Document every parameter of the Windows console wrapper methods, including private methods.  
  _evidence: review PR #1993 (https://github.com/Textualize/rich/pull/1993#discussion_r818482246)_
- [x] `f5072580-946e-4e61-a0a9-aea31c34d481` **Document user-facing changes and build documentation** — Consider updating documentation in `docs` for changes with user impact. Install documentation dependencies by running `pip install -r requirements.txt` from `docs`, then run `make docs` from the project root to generate HTML at `docs/build/html`.  
  _evidence: CONTRIBUTING.md:102-120_
- [ ] `c628ed4a-560c-4635-96f8-149b2fda837c` **FORCE_COLOR presence forces terminal mode** — In terminal detection, any defined FORCE_COLOR value, including an empty string, sets `_force_terminal` to True.  
  _evidence: review PR #2513 (https://github.com/Textualize/rich/pull/2513#discussion_r965880059)_
- [x] `bde2f406-ae8a-4fa1-b4c6-6ee682d64a29` **Inspect rendered objects defensively** — In pretty rendering, do not assume objects have `__class__` or `__module__`; use defensive `getattr` access. Do not derive qualified class names by slicing `str(class_)`, since that representation is unreliable.  
  _evidence: review PR #2366 (https://github.com/Textualize/rich/pull/2366#discussion_r909919091); review PR #2366 (https://github.com/Textualize/rich/pull/2366#discussion_r909431408)_
- [x] `230abd27-27aa-49e0-ace3-f3cc10b37e73` **Legacy Windows reserves a cell for newlines** — Legacy Windows terminals count a newline as occupying a cell. Subtract one from the available terminal width so the newline does not wrap onto the following line.  
  _evidence: review PR #2160 (https://github.com/Textualize/rich/pull/2160#discussion_r843638613)_
- [x] `26959533-b289-4075-ad27-294ddc614948` **Poetry development environment** — Rich uses Poetry for packaging and dependency management; enter the project's isolated environment with `poetry shell` and install dependencies with `poetry install`. Run the contribution guide's development commands inside that environment.  
  _evidence: CONTRIBUTING.md:9-39_
- [ ] `cfdda210-a6c4-4300-85cc-3dd404c9e1a3` **Preserve current Windows cursor size when changing visibility** — In hide_cursor and show_cursor, fetch the current cursor info, modify its visible flag, and set it back in a single operation. Do not cache the cursor size in the constructor, since users may change it after construction.  
  _evidence: review PR #2339 (https://github.com/Textualize/rich/pull/2339#discussion_r897888819)_
- [x] `98e59f86-fcfb-4a48-9e04-2a9340ce9e3a` **Preserve established private names for compatibility** — Avoid renaming established private identifiers solely to improve naming clarity, since downstream code may depend on them. This compatibility concern applies even to private names such as `_console` and `_check_buffer`.  
  _evidence: review PR #2170 (https://github.com/Textualize/rich/pull/2170#discussion_r842886179); review PR #2066 (https://github.com/Textualize/rich/pull/2066#discussion_r826989656)_
- [ ] `bb057080-6b87-4ac5-94ec-a65f6a104acf` **Preserve named tuple edge cases and custom representations** — Named tuple detection must support tuple subclasses and accept an empty tuple for _fields. When pretty-printing named tuples, respect an overridden __repr__ instead of applying default named tuple formatting.  
  _evidence: review PR #2031 (https://github.com/Textualize/rich/pull/2031#discussion_r821654282); review PR #2031 (https://github.com/Textualize/rich/pull/2031#discussion_r821652410); review PR #2031 (https://github.com/Textualize/rich/pull/2031#discussion_r820776944)_
- [ ] `5cc7d54d-e9f8-43fb-8a64-1237e76f1a8e` **Preserve optional logging keywords and empty-list overrides** — Keep RichHandler.KEYWORDS optional because callers may set it to None to disable keyword highlighting. When keywords is None, fall back to KEYWORDS; an explicit empty list disables highlighting, and highlighting should run only when the resolved list is nonempty.  
  _evidence: review PR #1919 (https://github.com/Textualize/rich/pull/1919#discussion_r805352923); review PR #1919 (https://github.com/Textualize/rich/pull/1919#discussion_r805352393); review PR #1919 (https://github.com/Textualize/rich/pull/1919#discussion_r804556120)_
- [x] `53f6b168-8b1c-4154-b39e-c92b517b4444` **Preserve pretty traversal for traceback locals** — Keep traceback local-variable processing integrated with `pretty.traverse`; bypassing it breaks advanced data-structure formatting and other Rich features.  
  _evidence: review PR #2414 (https://github.com/Textualize/rich/pull/2414#discussion_r927755674)_
- [ ] `98f3cf01-41c9-495f-a318-720812fb4267` **Preserve the module-based diagnostics command** — Keep python -m rich.diagnose as the command in bug-report instructions. Invoke report() from the module's __main__ block so this command provides the same diagnostic information.  
  _evidence: review PR #1917 (https://github.com/Textualize/rich/pull/1917#discussion_r799536112); review PR #1917 (https://github.com/Textualize/rich/pull/1917#discussion_r799530835)_
- [x] `d312dafa-d571-43d3-8ed9-fb8702e811f8` **Preserve Traceback serialization and captured state** — Keep Traceback trivially serializable; avoid retaining arbitrary renderables that compromise serialization or whose mutable state could become outdated before printing.  
  _evidence: review PR #3325 (https://github.com/Textualize/rich/pull/3325#discussion_r1661501924)_
- [ ] `8077743d-7314-46fa-abea-6817572af7bd` **Resolve Jupyter dimensions only when needed** — Look up JUPYTER_COLUMNS only when width is unset, using an explicit `if not width` guard. Keep Jupyter default dimensions in module-level constants, including JUPYTER_DEFAULT_COLUMNS = 115.  
  _evidence: review PR #2332 (https://github.com/Textualize/rich/pull/2332#discussion_r896531327); review PR #2332 (https://github.com/Textualize/rich/pull/2332#discussion_r896526117)_
- [x] `e56b03d7-5add-4a39-b141-cc5e6bace6d6` **Theme names, inheritance, and file format** — Theme style names must be lowercase, start with a letter, and contain only letters or '.', '-', and '_'. Theme inherits default styles unless inherit=False, overrides defaults by matching name, and supports reading external configuration files with a [styles] section through Theme.read.  
  _evidence: docs/source/style.rst:106-131; docs/source/style.rst:132-149; docs/source/style.rst:150-160_
- [ ] `8684aafb-901c-475f-9e30-24990bf0fdba` **Traceback control locals use truthiness** — Evaluate `_rich_traceback_omit` and `_rich_traceback_guard` by their values, defaulting to False when absent. Their presence alone should not trigger traceback control behavior.  
  _evidence: review PR #2226 (https://github.com/Textualize/rich/pull/2226#discussion_r858644223)_
- [ ] `ab1003f7-a386-4c78-bb75-e899f22dbc9e` **Use JSON-specific whitespace in highlighting** — When scanning whitespace in JSON highlighting, accept only whitespace permitted by the JSON specification rather than all characters in string.whitespace.  
  _evidence: review PR #2038 (https://github.com/Textualize/rich/pull/2038#discussion_r821815639)_
- [x] `738011f4-c157-4561-8c96-7327e9dac244` **Use relative imports within Rich** — Use relative imports for imports within the rich package to match the existing codebase.  
  _evidence: review PR #2977 (https://github.com/Textualize/rich/pull/2977#discussion_r1211778554)_
- [x] `a535d701-0dd5-4bb7-b527-21ceb711c5ac` **Use safe representations in exception handling** — Use `safe_repr` when obtaining object representations during traceback processing; direct `__repr__` calls can raise exceptions or return non-strings.  
  _evidence: review PR #2414 (https://github.com/Textualize/rich/pull/2414#discussion_r927752303)_
