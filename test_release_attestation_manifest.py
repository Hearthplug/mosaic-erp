import unittest


def verify(index, attestations):
    platforms = [m for m in index["manifests"] if m.get("platform", {}).get("os") == "linux" and m["platform"].get("architecture") in {"amd64", "arm64"}]
    refs = [m for m in index["manifests"] if m.get("annotations", {}).get("vnd.docker.reference.type") == "attestation-manifest"]
    if len(platforms) != 2 or len(refs) != 2:
        return False
    for platform in platforms:
        matching = [m for m in refs if m["annotations"].get("vnd.docker.reference.digest") == platform["digest"]]
        if len(matching) != 1:
            return False
        manifest = attestations.get(matching[0]["digest"])
        if not manifest or manifest.get("mediaType") != "application/vnd.oci.image.manifest.v1+json":
            return False
        if manifest.get("artifactType") != "application/vnd.docker.attestation.manifest.v1+json" or manifest.get("subject", {}).get("digest") != platform["digest"]:
            return False
        predicates = [layer.get("annotations", {}).get("in-toto.io/predicate-type") for layer in manifest.get("layers", []) if layer.get("mediaType") == "application/vnd.in-toto+json"]
        if predicates.count("https://spdx.dev/Document") != 1 or sum(str(p).startswith("https://slsa.dev/provenance/") for p in predicates) != 1:
            return False
    return True


class ReleaseAttestationManifestTest(unittest.TestCase):
    def setUp(self):
        self.index = {"manifests": [
            {"digest": "sha256:amd64", "platform": {"os": "linux", "architecture": "amd64"}},
            {"digest": "sha256:arm64", "platform": {"os": "linux", "architecture": "arm64"}},
            {"digest": "sha256:att-amd64", "platform": {"os": "unknown", "architecture": "unknown"}, "annotations": {"vnd.docker.reference.type": "attestation-manifest", "vnd.docker.reference.digest": "sha256:amd64"}},
            {"digest": "sha256:att-arm64", "platform": {"os": "unknown", "architecture": "unknown"}, "annotations": {"vnd.docker.reference.type": "attestation-manifest", "vnd.docker.reference.digest": "sha256:arm64"}},
        ]}
        self.attestations = {digest: {"mediaType": "application/vnd.oci.image.manifest.v1+json", "artifactType": "application/vnd.docker.attestation.manifest.v1+json", "subject": {"digest": subject}, "layers": [
            {"mediaType": "application/vnd.in-toto+json", "annotations": {"in-toto.io/predicate-type": "https://spdx.dev/Document"}},
            {"mediaType": "application/vnd.in-toto+json", "annotations": {"in-toto.io/predicate-type": "https://slsa.dev/provenance/v1"}},
        ]} for digest, subject in (("sha256:att-amd64", "sha256:amd64"), ("sha256:att-arm64", "sha256:arm64"))}

    def test_real_buildx_shape_passes(self):
        self.assertTrue(verify(self.index, self.attestations))

    def test_missing_predicate_fails_closed(self):
        self.attestations["sha256:att-amd64"]["layers"].pop()
        self.assertFalse(verify(self.index, self.attestations))

    def test_wrong_subject_fails_closed(self):
        self.attestations["sha256:att-arm64"]["subject"]["digest"] = "sha256:amd64"
        self.assertFalse(verify(self.index, self.attestations))

    def test_duplicate_attestation_fails_closed(self):
        duplicate = dict(self.index["manifests"][2])
        duplicate["digest"] = "sha256:duplicate"
        self.index["manifests"].append(duplicate)
        self.assertFalse(verify(self.index, self.attestations))


if __name__ == "__main__":
    unittest.main()
