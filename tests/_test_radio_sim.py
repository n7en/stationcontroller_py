"""Temporary smoke tests for the radio simulator modules."""
import sys
import pytest

sys.path.insert(0, ".")


class TestRigctldDispatch:
    def setup_method(self):
        from simulator.radio_sim import SimRadioState, SimRigctld
        self.state = SimRadioState()
        self.rig = SimRigctld(self.state)

    def _d(self, cmd):
        return self.rig._dispatch(cmd)

    def test_get_freq_default(self):
        assert self._d(r"\get_freq").startswith("14200000\n")

    def test_set_then_get_freq(self):
        self._d(r"\set_freq 7100000")
        assert self._d(r"\get_freq").startswith("7100000\n")

    def test_get_mode_default(self):
        assert self._d(r"\get_mode").startswith("USB\n2400\n")

    def test_set_then_get_mode(self):
        self._d(r"\set_mode CW 500")
        assert self._d(r"\get_mode").startswith("CW\n500\n")

    def test_get_ptt_default_off(self):
        assert self._d(r"\get_ptt").startswith("0\n")

    def test_set_ptt_on(self):
        self._d(r"\set_ptt 1")
        assert self._d(r"\get_ptt").startswith("1\n")

    def test_set_ptt_off(self):
        self.state.ptt = True
        self._d(r"\set_ptt 0")
        assert self._d(r"\get_ptt").startswith("0\n")

    def test_get_split_vfo_default(self):
        assert self._d(r"\get_split_vfo").startswith("0\n")

    def test_set_split_on(self):
        self._d(r"\set_split_vfo 1 VFOB")
        assert self._d(r"\get_split_vfo").startswith("1\n")

    def test_get_split_freq(self):
        self._d(r"\set_split_freq 14225000")
        assert self._d(r"\get_split_freq").startswith("14225000\n")

    def test_get_vfo(self):
        assert self._d(r"\get_vfo").startswith("VFOA\n")

    def test_set_vfo(self):
        self._d(r"\set_vfo VFOB")
        assert self._d(r"\get_vfo").startswith("VFOB\n")

    def test_get_level_rfpower(self):
        assert self._d(r"\get_level RFPOWER").startswith("1.000000\n")

    def test_set_then_get_level_rfpower(self):
        self._d(r"\set_level RFPOWER 0.75")
        assert self._d(r"\get_level RFPOWER").startswith("0.750000\n")

    def test_get_level_af(self):
        self._d(r"\set_level AF 0.3")
        assert self._d(r"\get_level AF").startswith("0.300000\n")

    def test_get_level_strength_returns_number(self):
        resp = self._d(r"\get_level STRENGTH")
        val = float(resp.splitlines()[0])
        assert -60 < val < 60

    def test_get_info(self):
        assert self._d(r"\get_info").startswith("SimRig\n")

    def test_unknown_command_returns_error(self):
        assert self._d(r"\set_something_unknown 42").startswith("RPRT -1")

    def test_empty_command_returns_error(self):
        assert self._d("").startswith("RPRT -1")

    def test_rprt_0_appended_to_all_get_responses(self):
        for cmd in [r"\get_freq", r"\get_mode", r"\get_vfo",
                    r"\get_ptt", r"\get_split_vfo", r"\get_info"]:
            assert "RPRT 0" in self._d(cmd), f"missing RPRT 0 in response to {cmd}"


class TestDCNSimulatorRadioIntegration:
    def test_rigctld_none_when_disabled(self):
        from simulator.dcn_sim import DCNSimulator
        cfg = {"mqtt": {"broker": "localhost", "port": 1883}, "devices": []}
        sim = DCNSimulator(cfg)
        assert sim._rigctld is None

    def test_rigctld_created_when_enabled(self):
        from simulator.dcn_sim import DCNSimulator
        cfg = {
            "mqtt": {"broker": "localhost", "port": 1883},
            "devices": [],
            "radio": {"rigctld": {
                "enabled": True, "host": "127.0.0.1", "port": 14532,
                "initial": {"frequency_hz": 7100000, "mode": "LSB"},
            }},
        }
        sim = DCNSimulator(cfg)
        assert sim._rigctld is not None
        assert sim._rigctld.state.frequency_hz == 7100000.0
        assert sim._rigctld.state.mode == "LSB"

    def test_rigctld_off_when_enabled_false_explicitly(self):
        from simulator.dcn_sim import DCNSimulator
        cfg = {
            "mqtt": {"broker": "localhost", "port": 1883},
            "devices": [],
            "radio": {"rigctld": {"enabled": False}},
        }
        sim = DCNSimulator(cfg)
        assert sim._rigctld is None


class TestHamlibShim:
    def setup_method(self):
        import simulator.Hamlib as H
        self.H = H
        self.rig = H.Rig(1)
        self.rig.open()

    def teardown_method(self):
        self.rig.close()

    def test_default_frequency(self):
        assert self.rig.get_freq(self.H.RIG_VFO_CURR) == 14_200_000.0

    def test_set_get_frequency(self):
        self.rig.set_freq(self.H.RIG_VFO_CURR, 3_573_000)
        assert self.rig.get_freq(self.H.RIG_VFO_CURR) == 3_573_000.0

    def test_default_mode_usb(self):
        mode, bw = self.rig.get_mode(self.H.RIG_VFO_CURR)
        assert mode == self.H.RIG_MODE_USB
        assert bw == 2400

    def test_set_get_mode(self):
        self.rig.set_mode(self.H.RIG_VFO_CURR, self.H.RIG_MODE_CW, 500)
        mode, bw = self.rig.get_mode(self.H.RIG_VFO_CURR)
        assert mode == self.H.RIG_MODE_CW
        assert bw == 500

    def test_ptt_default_off(self):
        assert self.rig.get_ptt(self.H.RIG_VFO_CURR) == self.H.RIG_PTT_OFF

    def test_set_ptt_on_off(self):
        self.rig.set_ptt(self.H.RIG_VFO_CURR, self.H.RIG_PTT_ON)
        assert self.rig.get_ptt(self.H.RIG_VFO_CURR) == self.H.RIG_PTT_ON
        self.rig.set_ptt(self.H.RIG_VFO_CURR, self.H.RIG_PTT_OFF)
        assert self.rig.get_ptt(self.H.RIG_VFO_CURR) == self.H.RIG_PTT_OFF

    def test_split_default_off(self):
        split, _ = self.rig.get_split_vfo(self.H.RIG_VFO_CURR)
        assert split == self.H.RIG_SPLIT_OFF

    def test_set_split_on(self):
        self.rig.set_split_vfo(self.H.RIG_VFO_CURR, self.H.RIG_SPLIT_ON, self.H.RIG_VFO_B)
        split, tx_vfo = self.rig.get_split_vfo(self.H.RIG_VFO_CURR)
        assert split == self.H.RIG_SPLIT_ON
        assert tx_vfo == self.H.RIG_VFO_B

    def test_split_freq(self):
        self.rig.set_split_freq(self.H.RIG_VFO_CURR, 14_225_000)
        assert self.rig.get_split_freq(self.H.RIG_VFO_CURR) == 14_225_000.0

    def test_rfpower_level(self):
        self.rig.set_level(self.H.RIG_VFO_CURR, self.H.RIG_LEVEL_RFPOWER, 0.6)
        assert self.rig.get_level_f(self.H.RIG_VFO_CURR, self.H.RIG_LEVEL_RFPOWER) == 0.6

    def test_strength_level_has_noise(self):
        # Just verify it returns a float without raising
        val = self.rig.get_level_f(self.H.RIG_VFO_CURR, self.H.RIG_LEVEL_STR)
        assert isinstance(val, float)

    @pytest.mark.parametrize("name,const", [
        ("USB", "RIG_MODE_USB"), ("LSB", "RIG_MODE_LSB"), ("CW", "RIG_MODE_CW"),
        ("CWR", "RIG_MODE_CWR"), ("AM", "RIG_MODE_AM"), ("FM", "RIG_MODE_FM"),
        ("FMN", "RIG_MODE_FMN"), ("WFM", "RIG_MODE_WFM"), ("RTTY", "RIG_MODE_RTTY"),
        ("RTTYR", "RIG_MODE_RTTYR"), ("PKTUSB", "RIG_MODE_PKTUSB"),
        ("PKTLSB", "RIG_MODE_PKTLSB"), ("PKTFM", "RIG_MODE_PKTFM"),
    ])
    def test_rig_strrmode_roundtrip(self, name, const):
        H = self.H
        assert H.rig_strrmode(getattr(H, const)) == name

    def test_rig_strvfo_vfoa(self):
        assert self.H.rig_strvfo(self.H.RIG_VFO_A) == "VFOA"

    def test_rig_strvfo_vfob(self):
        assert self.H.rig_strvfo(self.H.RIG_VFO_B) == "VFOB"

    def test_state_tree_settable(self):
        self.rig.state.rigport.pathname = "/dev/ttyUSB0"
        self.rig.state.rigport.parm.serial.rate = 38400
        self.rig.state.rigport.parm.serial.parity = self.H.RIG_PARITY_NONE
        assert self.rig.state.rigport.pathname == "/dev/ttyUSB0"
        assert self.rig.state.rigport.parm.serial.rate == 38400

    def test_get_info(self):
        info = self.rig.get_info()
        assert "SimRig" in info

    def test_multiple_rig_instances_independent(self):
        H = self.H
        r2 = H.Rig(351)
        r2.set_freq(H.RIG_VFO_CURR, 7_000_000)
        assert self.rig.get_freq(H.RIG_VFO_CURR) == 14_200_000.0
        assert r2.get_freq(H.RIG_VFO_CURR) == 7_000_000.0
