#! /usr/bin/perl

package ClassicalDB;

use JSON;
use Carp;
use strict;

# create a JSON object, just in case we want to use it more than once.
#my $json = new JSON();
my $json = JSON->new->allow_nonref;

sub parse {
    my $package = shift;
    my $file = shift;
    # print "Opening $file\n";
    open JSONFILE, "< " . $file or croak "Could not open $file";
    my @lines = <JSONFILE>;
    close JSONFILE;
    my $line = join("", @lines);
    my $obj = $json->decode($line);
    bless $obj;
    # print "Done parsing $file\n";
    return $obj;
}

sub getTrack {
    my ($obj, $trackNum, $set) = @_;
    my $result = {};
    $trackNum = int ($trackNum);
    $set      = int ($set) if defined $set;

	my $disc;

    my $works = $obj->{works};
    if (defined $works) {
        foreach my $work (@$works) {
			#print "WORK: $work->{TITLE} $work->{OPUS}\n";
			$disc = $work->{SET};
			$disc = $obj->{SET} unless defined $disc;

			## This first one should never match.
            if (($disc == $set) && ($work->{TRACKNUMBER} == $trackNum)) {
				setTags ($obj,  $result);
				setTags ($work, $result);
				return $result;
			}
			my $tracks = $work->{tracks};
			foreach my $track (@$tracks) {
				#print "TRACK: $track\n";
				$disc = $track->{SET} if defined($track->{SET});
				$disc = int($disc) if defined $disc;
				if (($disc == $set) && ($track->{TRACKNUMBER} == $trackNum)) {
					setTags ($obj,  $result);
					setTags ($work, $result);
					setTags ($track, $result);
					return $result;
				}
			}
		}
    } 
    my $tracks = $obj->{tracks};
    if (defined $tracks) {
        foreach my $track (@$tracks) {
			$disc = $track->{SET};
			$disc = $obj->{SET} unless defined $disc;
			$disc = int($disc) if defined $disc;
			#print $disc, "**", $track->{TRACKNUMBER}, "\n";
            if (($disc == $set) && ($track->{TRACKNUMBER} == $trackNum)) {
				setTags ($obj,  $result);
				setTags ($track, $result);
				return $result;
            }
		}
    }
    return undef;
}
 
sub setTags {
    my ($inHash, $outHash) = @_;
    foreach my $key (keys %$inHash) {
        next if ($key =~ /^[a-z0-9]+$/);
        next if ref ($inHash->{$key});
        # print "Found key $key\n";
        $outHash->{$key} = $inHash->{$key};
    }
}

sub numTracks {
    my $obj = shift;
    my $works = $obj->{works};
    my $numTracks = 0;
    if (defined $works) {
        foreach my $work (@$works) {
            if (defined $work->{TRACKNUMBER}) {
                my $trackNum = $work->{TRACKNUMBER};
                $numTracks = $trackNum if ($trackNum > $numTracks);
            } else {
                my $tracks = $work->{tracks};
                foreach my $track (@$tracks) {
                    my $trackNum = $track->{TRACKNUMBER};
                    $numTracks = $trackNum if ($trackNum > $numTracks);
                }
            }
        }
    }
    my $tracks = $obj->{tracks};
    if (defined $tracks) {
        foreach my $track (@$tracks) {
            my $trackNum = $track->{TRACKNUMBER};
            $numTracks = $trackNum if ($trackNum > $numTracks);
        }
    }
    return $numTracks;
}
1;
