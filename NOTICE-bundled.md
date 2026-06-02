## Bundled Binaries

The following third-party binaries are bundled with this application. They are
not pulled from npm, Cargo, or pip and therefore are not covered by the
automated license collectors. Their attributions are listed here.

### minimap2

minimap2 is bundled as a standalone executable for sequence alignment.
On Windows, minimap2 v2.30 is compiled from source with the MinGW-w64
toolchain and **statically linked** (no MinGW runtime DLL dependencies).
On Linux and macOS, the upstream binary is vendored.

- Project: https://github.com/lh3/minimap2
- License: MIT

```
The MIT License

Copyright (c) 2018-     Dana-Farber Cancer Institute
              2017-2018 Broad Institute, Inc.

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### zlib

zlib is statically linked into the Windows minimap2 build (via the
mingw-w64-x86_64-zlib package) for gzip/deflate (de)compression.

- Project: https://zlib.net/
- License: zlib license

```
zlib.h -- interface of the 'zlib' general purpose compression library

  Copyright (C) 1995-2024 Jean-loup Gailly and Mark Adler

  This software is provided 'as-is', without any express or implied
  warranty.  In no event will the authors be held liable for any damages
  arising from the use of this software.

  Permission is granted to anyone to use this software for any purpose,
  including commercial applications, and to alter it and redistribute it
  freely, subject to the following restrictions:

  1. The origin of this software must not be misrepresented; you must not
     claim that you wrote the original software. If you use this software
     in a product, an acknowledgment in the product documentation would be
     appreciated but is not required.
  2. Altered source versions must be plainly marked as such, and must not be
     misrepresented as being the original software.
  3. This notice may not be removed or altered from any source distribution.

  Jean-loup Gailly        Mark Adler
  jloup@gzip.org          madler@alumni.caltech.edu
```

> Note: The Windows static build also embeds GCC runtime support libraries
> (libgcc / libwinpthread from MinGW-w64). These carry the GCC Runtime
> Library Exception and a permissive MIT-style license respectively and
> impose no additional notice obligation; they are recorded here for
> completeness.
