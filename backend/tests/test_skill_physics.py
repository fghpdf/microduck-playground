import json
from pathlib import Path
import sys
import pytest
from ducklab.fast_runner import main
from ducklab.scenarios import get_scenario
from ducklab.skill_scoring import score_scene

@pytest.mark.parametrize('scene_id',['football_left','football_right','pickup_trash'])
def test_official_skill_physical_episode(scene_id,monkeypatch,capsys):
    root=Path(__file__).resolve().parents[2]
    monkeypatch.setattr(sys,'argv',['fast_runner','--rl',str(root.parent/'vendor/microduck_rl'),'--policies',str(root/'data/policies/current'),'--scenario',scene_id])
    main()
    rows=[json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{')]
    frames=[row for row in rows if row['type']=='frame']
    assert rows[-1]['type']=='done'
    score=score_scene(frames,get_scenario(scene_id))
    assert score['falls']==0
    if scene_id.startswith('football'):
        assert frames[-1]['t'] <= 3.5
        assert frames[-1]['t'] >= 3.0  # Preserve the complete official kick.
        assert score['success'] and score['details']['ball_contact']
        assert score['details']['ball_distance']>.1
        assert all(f['objects'][0]['position']==f['ball'] for f in frames)
    else:
        assert score['success']
        assert score['details']['picked_up']
        assert score['details']['transported']
        assert score['details']['placed']
        assert score['details']['peak_lift'] > .1
        held = [frame for frame in frames if frame.get('pickup', {}).get('attached')]
        assert held and held[0]['pickup']['contact_seen']
        released = [frame for frame in frames if frame.get('pickup', {}).get('released')]
        assert released and not released[-1]['objects'][0]['attached']
        assert abs(frames[-1]['objects'][0]['position'][0] - .6) < .12
        assert frames[-1]['objects'][0]['position'][2] < .025
        # A free object must move continuously, including after contact release.
        import math
        assert max(math.dist(a['objects'][0]['position'], b['objects'][0]['position'])
                   for a, b in zip(frames, frames[1:])) < .03
