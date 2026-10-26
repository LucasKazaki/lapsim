# Three.js compatibility pin

The unmodified `three-0.160.0.min.js` is the classic global build from official
Three.js tag **r160**, commit
`d04539a76736ff500cae883d6a38b3dd8643c548`. It is used by the standalone offline
replay and by Node scene-graph tests, without npm, a CDN or a system installation.

This is an **older compatibility pin**, not the latest version or a general
dependency recommendation. Upstream warns that classic builds are deprecated.
The chosen build preserves direct `file://` replay in the current classic-script
page; adopting a newer module build requires a separately reviewed module/bundle
delivery route. No such tooling is installed in this milestone.

`three-LICENSE.txt` is the complete unmodified MIT license. Keep it with the
library in every copy/package. `three-provenance.json` records the official
source commit and Git blob IDs; tests verify both files byte-for-byte.
Three.js remains third-party MIT material and is not relicensed by this project.

Primary API reference used for this exact pin:
https://github.com/mrdoob/three.js/blob/d04539a76736ff500cae883d6a38b3dd8643c548/docs/api/en/renderers/WebGLRenderer.html

The dependency provides the WebGL renderer, depth buffer, meshes/materials,
scene graph and cameras. Its presence and passing CPU tests do not establish
that this PC successfully created a browser WebGL context or compiled shaders.
