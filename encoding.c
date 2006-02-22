#include <stdio.h>
#include <stdlib.h>

// 10xxxxxx
#define	mask_UTF8trailer	0xc0
#define bits_UTF8trailer	0x80

// 110xxxxx
#define mask_UTF8leader1	0xe0
#define bits_UTF8leader1	0xc0

// 1110xxxx
#define mask_UTF8leader2	0xef
#define bits_UTF8leader2	0xe0

// 11110xx
#define mask_UTF8leader3	0xf8
#define bits_UTF8leader3	0xf0

int
checkEncoding(FILE	*file)
{
    int		utf8Length	= 0;
    int		validLatin1	= 1;
    int		validUTF8	= 1;
    int		nonASCII	= 0;
    int		a;

    while ((a = fgetc(file)) != EOF) {
	a = a & 0xff;
	if ((a & 0x80) == 0) {
	    if (utf8Length) { validUTF8 = 0; utf8Length = 0; }
	} else {
	    nonASCII = 1;
	    if (a < 0xa0) { validLatin1 = 0; }
	    if ((a & mask_UTF8trailer) == bits_UTF8trailer) {
		if (!utf8Length) { validUTF8 = 0; } else { utf8Length--; }
	    }
	    else if ((a & mask_UTF8leader1) == bits_UTF8leader1) {
		if (utf8Length) { validUTF8 = 0; } else { utf8Length = 1; }
	    }
	    else if ((a & mask_UTF8leader2) == bits_UTF8leader2) {
		if (utf8Length) { validUTF8 = 0; } else { utf8Length = 2; }
	    }
	    else if ((a & mask_UTF8leader3) == bits_UTF8leader3) {
		if (utf8Length) { validUTF8 = 0; } else { utf8Length = 3; }
	    } else {
		validUTF8 = 0;
	    }
	}
    }
    if (!nonASCII) {
	printf("ASCII\n");
    } else {
	if (validUTF8) printf("UTF8\n");
	else if (validLatin1) printf("Latin1\n");
	else printf ("Unknown\n");
    }
    return 0;
}

int
main(int argc, char **argv)
{
    int		i;
    int		printName = 0;
    FILE	*file;
    int		retCode = 0;

    if (argc == 1) {
	checkEncoding(stdin);
    } else {
	if (argc > 2) printName = 1;
	for (i = 1; i < argc; i++)
	{
	    file = fopen(argv[i], "r");
	    if (!file) {
		fprintf(stderr, "%s: Cannot open\n", argv[i]);
		retCode = 1;
		continue;
	    }
	    if (printName) printf("%-10s: ", argv[i]);
	    checkEncoding(file);
	    fclose(file);
	}
    }
    return retCode;
}
