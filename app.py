from flask import Flask, render_template, jsonify, request
import json
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import JSONFormatter

app = Flask(__name__)

# Create YouTubeTranscriptApi instance
ytt_api = YouTubeTranscriptApi()

# Available translations
TRANSLATIONS = ["NIV", "Hebrew"]

# Bible data with multiple translations
# KJV - King James Version (Primary)
BIBLE_KJV = {
    "Genesis": {
        1: {
            1: "In the beginning God created the heaven and the earth.",
            2: "And the earth was without form, and void; and darkness was upon the face of the deep. And the Spirit of God moved upon the face of the waters.",
            3: "And God said, Let there be light: and there was light.",
            4: "And God saw the light, that it was good: and God divided the light from the darkness.",
            5: "And God called the light Day, and the darkness he called Night. And the evening and the morning were the first day.",
            6: "And God said, Let there be a firmament in the midst of the waters, and let it divide the waters from the waters.",
            7: "And God made the firmament, and divided the waters which were under the firmament from the waters which were above the firmament: and it was so.",
            8: "And God called the firmament Heaven. And the evening and the morning were the second day.",
            9: "And God said, Let the waters under the heaven be gathered together unto one place, and let the dry land appear: and it was so.",
            10: "And God called the dry land Earth; and the gathering together of the waters called he Seas: and God saw that it was good.",
            11: "And God said, Let the earth bring forth grass, the herb yielding seed, and the fruit tree yielding fruit after his kind, whose seed is in itself, upon the earth: and it was so.",
            12: "And the earth brought forth grass, and herb yielding seed after his kind, and the tree yielding fruit, whose seed was in itself, after his kind: and God saw that it was good.",
            13: "And the evening and the morning were the third day.",
            14: "And God said, Let there be lights in the firmament of the heaven to divide the day from the night; and let them be for signs, and for seasons, and for days, and years:",
            15: "And let them be for lights in the firmament of the heaven to give light upon the earth: and it was so.",
            16: "And God made two great lights; the greater light to rule the day, and the lesser light to rule the night: he made the stars also.",
            17: "And God set them in the firmament of the heaven to give light upon the earth,",
            18: "And to rule over the day and over the night, and to divide the light from the darkness: and God saw that it was good.",
            19: "And the evening and the morning were the fourth day.",
            20: "And God said, Let the waters bring forth abundantly the moving creature that hath life, and fowl that may fly above the earth in the open firmament of heaven.",
            21: "And God created great whales, and every living creature that moveth, which the waters brought forth abundantly, after their kind, and every winged fowl after his kind: and God saw that it was good.",
            22: "And God blessed them, saying, Be fruitful, and multiply, and fill the waters in the seas, and let fowl multiply in the earth.",
            23: "And the evening and the morning were the fifth day.",
            24: "And God said, Let the earth bring forth the living creature after his kind, cattle, and creeping thing, and beast of the earth after his kind: and it was so.",
            25: "And God made the beast of the earth after his kind, and cattle after their kind, and every thing that creepeth upon the earth after his kind: and God saw that it was good.",
            26: "And God said, Let us make man in our image, after our likeness: and let them have dominion over the fish of the sea, and over the fowl of the air, and over the cattle, and over all the earth, and over every creeping thing that creepeth upon the earth.",
            27: "So God created man in his own image, in the image of God created he him; male and female created he them.",
            28: "And God blessed them, and God said unto them, Be fruitful, and multiply, and replenish the earth, and subdue it: and have dominion over the fish of the sea, and over the fowl of the air, and over every living thing that moveth upon the earth.",
            29: "And God said, Behold, I have given you every herb bearing seed, which is upon the face of all the earth, and every tree, in the which is the fruit of a tree yielding seed; to you it shall be for meat.",
            30: "And to every beast of the earth, and to every fowl of the air, and to every thing that creepeth upon the earth, wherein there is life, I have given every green herb for meat: and it was so.",
            31: "And God saw every thing that he had made, and, behold, it was very good. And the evening and the morning were the sixth day."
        },
        2: {
            1: "Thus the heavens and the earth were finished, and all the host of them.",
            2: "And on the seventh day God ended his work which he had made; and he rested on the seventh day from all his work which he had made.",
            3: "And God blessed the seventh day, and sanctified it: because that in it he had rested from all his work which God created and made.",
            4: "These are the generations of the heavens and of the earth when they were created, in the day that the LORD God made the earth and the heavens,",
            5: "And every plant of the field before it was in the earth, and every herb of the field before it grew: for the LORD God had not caused it to rain upon the earth, and there was not a man to till the ground.",
            6: "But there went up a mist from the earth, and watered the whole face of the ground.",
            7: "And the LORD God formed man of the dust of the ground, and breathed into his nostrils the breath of life; and man became a living soul.",
            8: "And the LORD God planted a garden eastward in Eden; and there he put the man whom he had formed.",
            9: "And out of the ground made the LORD God to grow every tree that is pleasant to the sight, and good for food; the tree of life also in the midst of the garden, and the tree of knowledge of good and evil.",
            10: "And a river went out of Eden to water the garden; and from thence it was parted, and became into four heads."
        }
    },
    "John": {
        1: {
            1: "In the beginning was the Word, and the Word was with God, and the Word was God.",
            2: "The same was in the beginning with God.",
            3: "All things were made by him; and without him was not any thing made that was made.",
            4: "In him was life; and the life was the light of men.",
            5: "And the light shineth in darkness; and the darkness comprehended it not.",
            6: "There was a man sent from God, whose name was John.",
            7: "The same came for a witness, to bear witness of the Light, that all men through him might believe.",
            8: "He was not that Light, but was sent to bear witness of that Light.",
            9: "That was the true Light, which lighteth every man that cometh into the world.",
            10: "He was in the world, and the world was made by him, and the world knew him not.",
            11: "He came unto his own, and his own received him not.",
            12: "But as many as received him, to them gave he power to become the sons of God, even to them that believe on his name:",
            13: "Which were born, not of blood, nor of the will of the flesh, nor of the will of man, but of God.",
            14: "And the Word was made flesh, and dwelt among us, (and we beheld his glory, the glory as of the only begotten of the Father,) full of grace and truth."
        },
        3: {
            16: "For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life.",
            17: "For God sent not his Son into the world to condemn the world; but that the world through him might be saved."
        }
    },
    "Psalms": {
        23: {
            1: "The LORD is my shepherd; I shall not want.",
            2: "He maketh me to lie down in green pastures: he leadeth me beside the still waters.",
            3: "He restoreth my soul: he leadeth me in the paths of righteousness for his name's sake.",
            4: "Yea, though I walk through the valley of the shadow of death, I will fear no evil: for thou art with me; thy rod and thy staff they comfort me.",
            5: "Thou preparest a table before me in the presence of mine enemies: thou anointest my head with oil; my cup runneth over.",
            6: "Surely goodness and mercy shall follow me all the days of my life: and I will dwell in the house of the LORD for ever."
        }
    },
    "Matthew": {
        1: {
            1: "The book of the generation of Jesus Christ, the son of David, the son of Abraham.",
            2: "Abraham begat Isaac; and Isaac begat Jacob; and Jacob begat Judas and his brethren;",
            3: "And Judas begat Phares and Zara of Thamar; and Phares begat Esrom; and Esrom begat Aram;",
            4: "And Aram begat Aminadab; and Aminadab begat Naasson; and Naasson begat Salmon;",
            5: "And Salmon begat Booz of Rachab; and Booz begat Obed of Ruth; and Obed begat Jesse;",
            6: "And Jesse begat David the king; and David the king begat Solomon of her that had been the wife of Urias;",
            7: "And Solomon begat Roboam; and Roboam begat Abia; and Abia begat Asa;",
            8: "And Asa begat Josaphat; and Josaphat begat Joram; and Joram begat Ozias;",
            9: "And Ozias begat Joatham; and Joatham begat Achaz; and Achaz begat Ezekias;",
            10: "And Ezekias begat Manasses; and Manasses begat Amon; and Amon begat Josias;",
            11: "And Josias begat Jechonias and his brethren, about the time they were carried away to Babylon:",
            12: "And after they were brought to Babylon, Jechonias begat Salathiel; and Salathiel begat Zorobabel;",
            13: "And Zorobabel begat Abiud; and Abiud begat Eliakim; and Eliakim begat Azor;",
            14: "And Azor begat Sadoc; and Sadoc begat Achim; and Achim begat Eliud;",
            15: "And Eliud begat Eleazar; and Eleazar begat Matthan; and Matthan begat Jacob;",
            16: "And Jacob begat Joseph the husband of Mary, of whom was born Jesus, who is called Christ.",
            17: "So all the generations from Abraham to David are fourteen generations; and from David until the carrying away into Babylon are fourteen generations; and from the carrying away into Babylon unto Christ are fourteen generations.",
            18: "Now the birth of Jesus Christ was on this wise: When as his mother Mary was espoused to Joseph, before they came together, she was found with child of the Holy Ghost.",
            19: "Then Joseph her husband, being a just man, and not willing to make her a publick example, was minded to put her away privily.",
            20: "But while he thought on these things, behold, the angel of the Lord appeared unto him in a dream, saying, Joseph, thou son of David, fear not to take unto thee Mary thy wife: for that which is conceived in her is of the Holy Ghost.",
            21: "And she shall bring forth a son, and thou shalt call his name JESUS: for he shall save his people from their sins.",
            22: "Now all this was done, that it might be fulfilled which was spoken of the Lord by the prophet, saying,",
            23: "Behold, a virgin shall be with child, and shall bring forth a son, and they shall call his name Emmanuel, which being interpreted is, God with us.",
            24: "Then Joseph being raised from sleep did as the angel of the Lord had bidden him, and took unto him his wife:",
            25: "And knew her not till she had brought forth her firstborn son: and he called his name JESUS."
        },
        2: {
            1: "Now when Jesus was born in Bethlehem of Judaea in the days of Herod the king, behold, there came wise men from the east to Jerusalem,",
            2: "Saying, Where is he that is born King of the Jews? for we have seen his star in the east, and are come to worship him.",
            3: "When Herod the king had heard these things, he was troubled, and all Jerusalem with him.",
            4: "And when he had gathered all the chief priests and scribes of the people together, he demanded of them where Christ should be born.",
            5: "And they said unto him, In Bethlehem of Judaea: for thus it is written by the prophet,",
            6: "And thou Bethlehem, in the land of Juda, art not the least among the princes of Juda: for out of thee shall come a Governor, that shall rule my people Israel.",
            7: "Then Herod, when he had privily called the wise men, enquired of them diligently what time the star appeared.",
            8: "And he sent them to Bethlehem, and said, Go and search diligently for the young child; and when ye have found him, bring me word again, that I may come and worship him also.",
            9: "When they had heard the king, they departed; and, lo, the star, which they saw in the east, went before them, till it came and stood over where the young child was.",
            10: "When they saw the star, they rejoiced with exceeding great joy.",
            11: "And when they were come into the house, they saw the young child with Mary his mother, and fell down, and worshipped him: and when they had opened their treasures, they presented unto him gifts; gold, and frankincense and myrrh.",
            12: "And being warned of God in a dream that they should not return to Herod, they departed into their own country another way.",
            13: "And when they were departed, behold, the angel of the Lord appeareth to Joseph in a dream, saying, Arise, and take the young child and his mother, and flee into Egypt, and be thou there until I bring thee word: for Herod will seek the young child to destroy him.",
            14: "When he arose, he took the young child and his mother by night, and departed into Egypt:",
            15: "And was there until the death of Herod: that it might be fulfilled which was spoken of the Lord by the prophet, saying, Out of Egypt have I called my son.",
            16: "Then Herod, when he saw that he was mocked of the wise men, was exceeding wroth, and sent forth, and slew all the children that were in Bethlehem, and in all the coasts thereof, from two years old and under, according to the time which he had diligently enquired of the wise men.",
            17: "Then was fulfilled that which was spoken by Jeremy the prophet, saying,",
            18: "In Rama was there a voice heard, lamentation, and weeping, and great mourning, Rachel weeping for her children, and would not be comforted, because they are not.",
            19: "But when Herod was dead, behold, an angel of the Lord appeareth in a dream to Joseph in Egypt,",
            20: "Saying, Arise, and take the young child and his mother, and go into the land of Israel: for they are dead which sought the young child's life.",
            21: "And he arose, and took the young child and his mother, and came into the land of Israel.",
            22: "But when he heard that Archelaus did reign in Judaea in the room of his father Herod, he was afraid to go thither: notwithstanding, being warned of God in a dream, he turned aside into the parts of Galilee:",
            23: "And he came and dwelt in a city called Nazareth: that it might be fulfilled which was spoken by the prophets, He shall be called a Nazarene."
        },
        3: {
            1: "In those days came John the Baptist, preaching in the wilderness of Judaea,",
            2: "And saying, Repent ye: for the kingdom of heaven is at hand.",
            3: "For this is he that was spoken of by the prophet Esaias, saying, The voice of one crying in the wilderness, Prepare ye the way of the Lord, make his paths straight.",
            4: "And the same John had his raiment of camel's hair, and a leathern girdle about his loins; and his meat was locusts and wild honey.",
            5: "Then went out to him Jerusalem, and all Judaea, and all the region round about Jordan,",
            6: "And were baptized of him in Jordan, confessing their sins.",
            7: "But when he saw many of the Pharisees and Sadducees come to his baptism, he said unto them, O generation of vipers, who hath warned you to flee from the wrath to come?",
            8: "Bring forth therefore fruits meet for repentance:",
            9: "And think not to say within yourselves, We have Abraham to our father: for I say unto you, that God is able of these stones to raise up children unto Abraham.",
            10: "And now also the axe is laid unto the root of the trees: therefore every tree which bringeth not forth good fruit is hewn down, and cast into the fire.",
            11: "I indeed baptize you with water unto repentance: but he that cometh after me is mightier than I, whose shoes I am not worthy to bear: he shall baptize you with the Holy Ghost, and with fire:",
            12: "Whose fan is in his hand, and he will throughly purge his floor, and gather his wheat into the garner; but he will burn up the chaff with unquenchable fire.",
            13: "Then cometh Jesus from Galilee to Jordan unto John, to be baptized of him.",
            14: "But John forbad him, saying, I have need to be baptized of thee, and comest thou to me?",
            15: "And Jesus answering said unto him, Suffer it to be so now: for thus it becometh us to fulfil all righteousness. Then he suffered him.",
            16: "And Jesus, when he was baptized, went up straightway out of the water: and, lo, the heavens were opened unto him, and he saw the Spirit of God descending like a dove, and lighting upon him:",
            17: "And lo a voice from heaven, saying, This is my beloved Son, in whom I am well pleased."
        },
        4: {
            1: "Then was Jesus led up of the Spirit into the wilderness to be tempted of the devil.",
            2: "And when he had fasted forty days and forty nights, he was afterward an hungred.",
            3: "And when the tempter came to him, he said, If thou be the Son of God, command that these stones be made bread.",
            4: "But he answered and said, It is written, Man shall not live by bread alone, but by every word that proceedeth out of the mouth of God.",
            5: "Then the devil taketh him up into the holy city, and setteth him on a pinnacle of the temple,",
            6: "And saith unto him, If thou be the Son of God, cast thyself down: for it is written, He shall give his angels charge concerning thee: and in their hands they shall bear thee up, lest at any time thou dash thy foot against a stone.",
            7: "Jesus said unto him, It is written again, Thou shalt not tempt the Lord thy God.",
            8: "Again, the devil taketh him up into an exceeding high mountain, and sheweth him all the kingdoms of the world, and the glory of them;",
            9: "And saith unto him, All these things will I give thee, if thou wilt fall down and worship me.",
            10: "Then saith Jesus unto him, Get thee hence, Satan: for it is written, Thou shalt worship the Lord thy God, and him only shalt thou serve.",
            11: "Then the devil leaveth him, and, behold, angels came and ministered unto him.",
            12: "Now when Jesus had heard that John was cast into prison, he departed into Galilee;",
            13: "And leaving Nazareth, he came and dwelt in Capernaum, which is upon the sea coast, in the borders of Zabulon and Nephthalim:",
            14: "That it might be fulfilled which was spoken by Esaias the prophet, saying,",
            15: "The land of Zabulon, and the land of Nephthalim, by the way of the sea, beyond Jordan, Galilee of the Gentiles;",
            16: "The people which sat in darkness saw great light; and to them which sat in the region and shadow of death light is sprung up.",
            17: "From that time Jesus began to preach, and to say, Repent: for the kingdom of heaven is at hand.",
            18: "And Jesus, walking by the sea of Galilee, saw two brethren, Simon called Peter, and Andrew his brother, casting a net into the sea: for they were fishers.",
            19: "And he saith unto them, Follow me, and I will make you fishers of men.",
            20: "And they straightway left their nets, and followed him.",
            21: "And going on from thence, he saw other two brethren, James the son of Zebedee, and John his brother, in a ship with Zebedee their father, mending their nets; and he called them.",
            22: "And they immediately left the ship and their father, and followed him.",
            23: "And Jesus went about all Galilee, teaching in their synagogues, and preaching the gospel of the kingdom, and healing all manner of sickness and all manner of disease among the people.",
            24: "And his fame went throughout all Syria: and they brought unto him all sick people that were taken with divers diseases and torments, and those which were possessed with devils, and those which were lunatick, and those that had the palsy; and he healed them.",
            25: "And there followed him great multitudes of people from Galilee, and from Decapolis, and from Jerusalem, and from Judaea, and from beyond Jordan."
        }
    }
}

# NIV - New International Version
BIBLE_NIV = {
    "Genesis": {
        1: {
            1: "In the beginning God created the heavens and the earth.",
            2: "Now the earth was formless and empty, darkness was over the surface of the deep, and the Spirit of God was hovering over the waters.",
            3: "And God said, \"Let there be light,\" and there was light.",
            4: "God saw that the light was good, and he separated the light from the darkness.",
            5: "God called the light \"day,\" and the darkness he called \"night.\" And there was evening, and there was morning—the first day.",
            6: "And God said, \"Let there be a vault between the waters to separate water from water.\"",
            7: "So God made the vault and separated the water under the vault from the water above it. And it was so.",
            8: "God called the vault \"sky.\" And there was evening, and there was morning—the second day.",
            9: "And God said, \"Let the water under the sky be gathered to one place, and let dry ground appear.\" And it was so.",
            10: "God called the dry ground \"land,\" and the gathered waters he called \"seas.\" And God saw that it was good.",
            11: "Then God said, \"Let the land produce vegetation: seed-bearing plants and trees on the land that bear fruit with seed in it, according to their various kinds.\" And it was so.",
            12: "The land produced vegetation: plants bearing seed according to their kinds and trees bearing fruit with seed in it according to their kinds. And God saw that it was good.",
            13: "And there was evening, and there was morning—the third day.",
            14: "And God said, \"Let there be lights in the vault of the sky to separate the day from the night, and let them serve as signs to mark sacred times, and days and years,",
            15: "and let them be lights in the vault of the sky to give light on the earth.\" And it was so.",
            16: "God made two great lights—the greater light to govern the day and the lesser light to govern the night. He also made the stars.",
            17: "God set them in the vault of the sky to give light on the earth,",
            18: "to govern the day and the night, and to separate light from darkness. And God saw that it was good.",
            19: "And there was evening, and there was morning—the fourth day.",
            20: "And God said, \"Let the water teem with living creatures, and let birds fly above the earth across the vault of the sky.\"",
            21: "So God created the great creatures of the sea and every living thing with which the water teems and that moves about in it, according to their kinds, and every winged bird according to its kind. And God saw that it was good.",
            22: "God blessed them and said, \"Be fruitful and increase in number and fill the water in the seas, and let the birds increase on the earth.\"",
            23: "And there was evening, and there was morning—the fifth day.",
            24: "And God said, \"Let the land produce living creatures according to their kinds: the livestock, the creatures that move along the ground, and the wild animals, each according to its kind.\" And it was so.",
            25: "God made the wild animals according to their kinds, the livestock according to their kinds, and all the creatures that move along the ground according to their kinds. And God saw that it was good.",
            26: "Then God said, \"Let us make mankind in our image, in our likeness, so that they may rule over the fish in the sea and the birds in the sky, over the livestock and all the wild animals, and over all the creatures that move along the ground.\"",
            27: "So God created mankind in his own image, in the image of God he created them; male and female he created them.",
            28: "God blessed them and said to them, \"Be fruitful and increase in number; fill the earth and subdue it. Rule over the fish in the sea and the birds in the sky and over every living creature that moves on the ground.\"",
            29: "Then God said, \"I give you every seed-bearing plant on the face of the whole earth and every tree that has fruit with seed in it. They will be yours for food.",
            30: "And to all the beasts of the earth and all the birds in the sky and all the creatures that move along the ground—everything that has the breath of life in it—I give every green plant for food.\" And it was so.",
            31: "God saw all that he had made, and it was very good. And there was evening, and there was morning—the sixth day."
        },
        2: {
            1: "Thus the heavens and the earth were completed in all their vast array.",
            2: "By the seventh day God had finished the work he had been doing; so on the seventh day he rested from all his work.",
            3: "Then God blessed the seventh day and made it holy, because on it he rested from all the work of creating that he had done.",
            4: "This is the account of the heavens and the earth when they were created, when the LORD God made the earth and the heavens.",
            5: "Now no shrub had yet appeared on the earth and no plant had yet sprung up, for the LORD God had not sent rain on the earth and there was no one to work the ground,",
            6: "but streams came up from the earth and watered the whole surface of the ground.",
            7: "Then the LORD God formed a man from the dust of the ground and breathed into his nostrils the breath of life, and the man became a living being.",
            8: "Now the LORD God had planted a garden in the east, in Eden; and there he put the man he had formed.",
            9: "The LORD God made all kinds of trees grow out of the ground—trees that were pleasing to the eye and good for food. In the middle of the garden were the tree of life and the tree of the knowledge of good and evil.",
            10: "A river watering the garden flowed from Eden; from there it was separated into four headwaters."
        }
    },
    "John": {
        1: {
            1: "In the beginning was the Word, and the Word was with God, and the Word was God.",
            2: "He was with God in the beginning.",
            3: "Through him all things were made; without him nothing was made that has been made.",
            4: "In him was life, and that life was the light of all mankind.",
            5: "The light shines in the darkness, and the darkness has not overcome it.",
            6: "There was a man sent from God whose name was John.",
            7: "He came as a witness to testify concerning that light, so that through him all might believe.",
            8: "He himself was not the light; he came only as a witness to the light.",
            9: "The true light that gives light to everyone was coming into the world.",
            10: "He was in the world, and though the world was made through him, the world did not recognize him.",
            11: "He came to that which was his own, but his own did not receive him.",
            12: "Yet to all who did receive him, to those who believed in his name, he gave the right to become children of God—",
            13: "children born not of natural descent, nor of human decision or a husband's will, but born of God.",
            14: "The Word became flesh and made his dwelling among us. We have seen his glory, the glory of the one and only Son, who came from the Father, full of grace and truth."
        },
        3: {
            16: "For God so loved the world that he gave his one and only Son, that whoever believes in him shall not perish but have eternal life.",
            17: "For God did not send his Son into the world to condemn the world, but to save the world through him."
        }
    },
    "Psalms": {
        23: {
            1: "The LORD is my shepherd, I lack nothing.",
            2: "He makes me lie down in green pastures, he leads me beside quiet waters,",
            3: "he refreshes my soul. He guides me along the right paths for his name's sake.",
            4: "Even though I walk through the darkest valley, I will fear no evil, for you are with me; your rod and your staff, they comfort me.",
            5: "You prepare a table before me in the presence of my enemies. You anoint my head with oil; my cup overflows.",
            6: "Surely your goodness and love will follow me all the days of my life, and I will dwell in the house of the LORD forever."
        }
    },
    "Matthew": {
        1: {
            1: "This is the genealogy of Jesus the Messiah the son of David, the son of Abraham:",
            2: "Abraham was the father of Isaac, Isaac the father of Jacob, Jacob the father of Judah and his brothers,",
            3: "Judah the father of Perez and Zerah, whose mother was Tamar, Perez the father of Hezron, Hezron the father of Ram,",
            4: "Ram the father of Amminadab, Amminadab the father of Nahshon, Nahshon the father of Salmon,",
            5: "Salmon the father of Boaz, whose mother was Rahab, Boaz the father of Obed, whose mother was Ruth, Obed the father of Jesse,",
            6: "and Jesse the father of King David. David was the father of Solomon, whose mother had been Uriah's wife,",
            7: "Solomon the father of Rehoboam, Rehoboam the father of Abijah, Abijah the father of Asa,",
            8: "Asa the father of Jehoshaphat, Jehoshaphat the father of Jehoram, Jehoram the father of Uzziah,",
            9: "Uzziah the father of Jotham, Jotham the father of Ahaz, Ahaz the father of Hezekiah,",
            10: "Hezekiah the father of Manasseh, Manasseh the father of Amon, Amon the father of Josiah,",
            11: "and Josiah the father of Jeconiah and his brothers at the time of the exile to Babylon.",
            12: "After the exile to Babylon: Jeconiah was the father of Shealtiel, Shealtiel the father of Zerubbabel,",
            13: "Zerubbabel the father of Abihud, Abihud the father of Eliakim, Eliakim the father of Azor,",
            14: "Azor the father of Zadok, Zadok the father of Akim, Akim the father of Elihud,",
            15: "Elihud the father of Eleazar, Eleazar the father of Matthan, Matthan the father of Jacob,",
            16: "and Jacob the father of Joseph, the husband of Mary, and Mary was the mother of Jesus who is called the Messiah.",
            17: "Thus there were fourteen generations in all from Abraham to David, fourteen from David to the exile to Babylon, and fourteen from the exile to the Messiah.",
            18: "This is how the birth of Jesus the Messiah came about: His mother Mary was pledged to be married to Joseph, but before they came together, she was found to be pregnant through the Holy Spirit.",
            19: "Because Joseph her husband was faithful to the law, and yet did not want to expose her to public disgrace, he had in mind to divorce her quietly.",
            20: "But after he had considered this, an angel of the Lord appeared to him in a dream and said, \"Joseph son of David, do not be afraid to take Mary home as your wife, because what is conceived in her is from the Holy Spirit.",
            21: "She will give birth to a son, and you are to give him the name Jesus, because he will save his people from their sins.\"",
            22: "All this took place to fulfill what the Lord had said through the prophet:",
            23: "\"The virgin will conceive and give birth to a son, and they will call him Immanuel\" (which means \"God with us\").",
            24: "When Joseph woke up, he did what the angel of the Lord had commanded him and took Mary home as his wife.",
            25: "But he did not consummate their marriage until she gave birth to a son. And he gave him the name Jesus."
        },
        2: {
            1: "After Jesus was born in Bethlehem in Judea, during the time of King Herod, Magi from the east came to Jerusalem",
            2: "and asked, \"Where is the one who has been born king of the Jews? We saw his star when it rose and have come to worship him.\"",
            3: "When King Herod heard this he was disturbed, and all Jerusalem with him.",
            4: "When he had called together all the people's chief priests and teachers of the law, he asked them where the Messiah was to be born.",
            5: "\"In Bethlehem in Judea,\" they replied, \"for this is what the prophet has written:",
            6: "\"'But you, Bethlehem, in the land of Judah, are by no means least among the rulers of Judah; for out of you will come a ruler who will shepherd my people Israel.'\"",
            7: "Then Herod called the Magi secretly and found out from them the exact time the star had appeared.",
            8: "He sent them to Bethlehem and said, \"Go and search carefully for the child. As soon as you find him, report to me, so that I too may go and worship him.\"",
            9: "After they had heard the king, they went on their way, and the star they had seen when it rose went ahead of them until it stopped over the place where the child was.",
            10: "When they saw the star, they were overjoyed.",
            11: "On coming to the house, they saw the child with his mother Mary, and they bowed down and worshiped him. Then they opened their treasures and presented him with gifts of gold, frankincense and myrrh.",
            12: "And having been warned in a dream not to go back to Herod, they returned to their country by another route.",
            13: "When they had gone, an angel of the Lord appeared to Joseph in a dream. \"Get up,\" he said, \"take the child and his mother and escape to Egypt. Stay there until I tell you, for Herod is going to search for the child to kill him.\"",
            14: "So he got up, took the child and his mother during the night and left for Egypt,",
            15: "where he stayed until the death of Herod. And so was fulfilled what the Lord had said through the prophet: \"Out of Egypt I called my son.\"",
            16: "When Herod realized that he had been outwitted by the Magi, he was furious, and he gave orders to kill all the boys in Bethlehem and its vicinity who were two years old and under, in accordance with the time he had learned from the Magi.",
            17: "Then what was said through the prophet Jeremiah was fulfilled:",
            18: "\"A voice is heard in Ramah, weeping and great mourning, Rachel weeping for her children and refusing to be comforted, because they are no more.\"",
            19: "After Herod died, an angel of the Lord appeared in a dream to Joseph in Egypt",
            20: "and said, \"Get up, take the child and his mother and go to the land of Israel, for those who were trying to take the child's life are dead.\"",
            21: "So he got up, took the child and his mother and went to the land of Israel.",
            22: "But when he heard that Archelaus was reigning in Judea in place of his father Herod, he was afraid to go there. Having been warned in a dream, he withdrew to the district of Galilee,",
            23: "and he went and lived in a town called Nazareth. So was fulfilled what was said through the prophets, that he would be called a Nazarene."
        },
        3: {
            1: "In those days John the Baptist came, preaching in the wilderness of Judea",
            2: "and saying, \"Repent, for the kingdom of heaven has come near.\"",
            3: "This is he who was spoken of through the prophet Isaiah: \"A voice of one calling in the wilderness, 'Prepare the way for the Lord, make straight paths for him.'\"",
            4: "John's clothes were made of camel's hair, and he had a leather belt around his waist. His food was locusts and wild honey.",
            5: "People went out to him from Jerusalem and all Judea and the whole region of the Jordan.",
            6: "Confessing their sins, they were baptized by him in the Jordan River.",
            7: "But when he saw many of the Pharisees and Sadducees coming to where he was baptizing, he said to them: \"You brood of vipers! Who warned you to flee from the coming wrath?",
            8: "Produce fruit in keeping with repentance.",
            9: "And do not think you can say to yourselves, 'We have Abraham as our father.' I tell you that out of these stones God can raise up children for Abraham.",
            10: "The ax is already at the root of the trees, and every tree that does not produce good fruit will be cut down and thrown into the fire.",
            11: "\"I baptize you with water for repentance. But after me comes one who is more powerful than I, whose sandals I am not worthy to carry. He will baptize you with the Holy Spirit and fire.",
            12: "His winnowing fork is in his hand, and he will clear his threshing floor, gathering his wheat into the barn and burning up the chaff with unquenchable fire.\"",
            13: "Then Jesus came from Galilee to the Jordan to be baptized by John.",
            14: "But John tried to deter him, saying, \"I need to be baptized by you, and do you come to me?\"",
            15: "Jesus replied, \"Let it be so now; it is proper for us to do this to fulfill all righteousness.\" Then John consented.",
            16: "As soon as Jesus was baptized, he went up out of the water. At that moment heaven was opened, and he saw the Spirit of God descending like a dove and alighting on him.",
            17: "And a voice from heaven said, \"This is my Son, whom I love; with him I am well pleased.\""
        },
        4: {
            1: "Then Jesus was led by the Spirit into the wilderness to be tempted by the devil.",
            2: "After fasting forty days and forty nights, he was hungry.",
            3: "The tempter came to him and said, \"If you are the Son of God, tell these stones to become bread.\"",
            4: "Jesus answered, \"It is written: 'Man shall not live on bread alone, but on every word that comes from the mouth of God.'\"",
            5: "Then the devil took him to the holy city and had him stand on the highest point of the temple.",
            6: "\"If you are the Son of God,\" he said, \"throw yourself down. For it is written: \"'He will command his angels concerning you, and they will lift you up in their hands, so that you will not strike your foot against a stone.'\"",
            7: "Jesus answered him, \"It is also written: 'Do not put the Lord your God to the test.'\"",
            8: "Again, the devil took him to a very high mountain and showed him all the kingdoms of the world and their splendor.",
            9: "\"All this I will give you,\" he said, \"if you will bow down and worship me.\"",
            10: "Jesus said to him, \"Away from me, Satan! For it is written: 'Worship the Lord your God, and serve him only.'\"",
            11: "Then the devil left him, and angels came and attended him.",
            12: "When Jesus heard that John had been put in prison, he withdrew to Galilee.",
            13: "Leaving Nazareth, he went and lived in Capernaum, which was by the lake in the area of Zebulun and Naphtali—",
            14: "to fulfill what was said through the prophet Isaiah:",
            15: "\"Land of Zebulun and land of Naphtali, the Way of the Sea, beyond the Jordan, Galilee of the Gentiles—",
            16: "the people living in darkness have seen a great light; on those living in the land of the shadow of death a light has dawned.\"",
            17: "From that time on Jesus began to preach, \"Repent, for the kingdom of heaven has come near.\"",
            18: "As Jesus was walking beside the Sea of Galilee, he saw two brothers, Simon called Peter and his brother Andrew. They were casting a net into the lake, for they were fishermen.",
            19: "\"Come, follow me,\" Jesus said, \"and I will send you out to fish for people.\"",
            20: "At once they left their nets and followed him.",
            21: "Going on from there, he saw two other brothers, James son of Zebedee and his brother John. They were in a boat with their father Zebedee, preparing their nets. Jesus called them,",
            22: "and immediately they left the boat and their father and followed him.",
            23: "Jesus went throughout Galilee, teaching in their synagogues, proclaiming the good news of the kingdom, and healing every disease and sickness among the people.",
            24: "News about him spread all over Syria, and people brought to him all who were ill with various diseases, those suffering severe pain, the demon-possessed, those having seizures, and the paralyzed; and he healed them.",
            25: "Large crowds from Galilee, the Decapolis, Jerusalem, Judea and the region across the Jordan followed him."
        },
        5: {
            1: "Now when Jesus saw the crowds, he went up on a mountainside and sat down. His disciples came to him,",
            2: "and he began to teach them. He said:",
            3: "\"Blessed are the poor in spirit, for theirs is the kingdom of heaven.",
            4: "Blessed are those who mourn, for they will be comforted.",
            5: "Blessed are the meek, for they will inherit the earth.",
            6: "Blessed are those who hunger and thirst for righteousness, for they will be filled.",
            7: "Blessed are the merciful, for they will be shown mercy.",
            8: "Blessed are the pure in heart, for they will see God.",
            9: "Blessed are the peacemakers, for they will be called children of God.",
            10: "Blessed are those who are persecuted because of righteousness, for theirs is the kingdom of heaven.",
            11: "\"Blessed are you when people insult you, persecute you and falsely say all kinds of evil against you because of me.",
            12: "Rejoice and be glad, because great is your reward in heaven, for in the same way they persecuted the prophets who were before you.",
            13: "\"You are the salt of the earth. But if the salt loses its saltiness, how can it be made salty again? It is no longer good for anything, except to be thrown out and trampled underfoot.",
            14: "\"You are the light of the world. A town built on a hill cannot be hidden.",
            15: "Neither do people light a lamp and put it under a bowl. Instead they put it on its stand, and it gives light to everyone in the house.",
            16: "In the same way, let your light shine before others, that they may see your good deeds and glorify your Father in heaven.",
            17: "\"Do not think that I have come to abolish the Law or the Prophets; I have not come to abolish them but to fulfill them.",
            18: "For truly I tell you, until heaven and earth disappear, not the smallest letter, not the least stroke of a pen, will by any means disappear from the Law until everything is accomplished.",
            19: "Therefore anyone who sets aside one of the least of these commands and teaches others accordingly will be called least in the kingdom of heaven, but whoever practices and teaches these commands will be called great in the kingdom of heaven.",
            20: "For I tell you that unless your righteousness surpasses that of the Pharisees and the teachers of the law, you will certainly not enter the kingdom of heaven.",
            21: "\"You have heard that it was said to the people long ago, 'You shall not murder, and anyone who murders will be subject to judgment.'",
            22: "But I tell you that anyone who is angry with a brother or sister will be subject to judgment. Again, anyone who says to a brother or sister, 'Raca,' is answerable to the Sanhedrin. And anyone who says, 'You fool!' will be in danger of the fire of hell.",
            23: "\"Therefore, if you are offering your gift at the altar and there remember that your brother or sister has something against you,",
            24: "leave your gift there in front of the altar. First go and be reconciled to them; then come and offer your gift.",
            25: "\"Settle matters quickly with your adversary who is taking you to court. Do it while you are still together on the way, or your adversary may hand you over to the judge, and the judge may hand you over to the officer, and you may be thrown into prison.",
            26: "Truly I tell you, you will not get out until you have paid the last penny.",
            27: "\"You have heard that it was said, 'You shall not commit adultery.'",
            28: "But I tell you that anyone who looks at a woman lustfully has already committed adultery with her in his heart.",
            29: "\"If your right eye causes you to stumble, gouge it out and throw it away. It is better for you to lose one part of your body than for your whole body to be thrown into hell.",
            30: "And if your right hand causes you to stumble, cut it off and throw it away. It is better for you to lose one part of your body than for your whole body to go into hell.",
            31: "\"It has been said, 'Anyone who divorces his wife must give her a certificate of divorce.'",
            32: "But I tell you that anyone who divorces his wife, except for sexual immorality, makes her the victim of adultery, and anyone who marries a divorced woman commits adultery.",
            33: "\"Again, you have heard that it was said to the people long ago, 'Do not break your oath, but fulfill to the Lord the vows you have made.'",
            34: "But I tell you, do not swear an oath at all: either by heaven, for it is God's throne;",
            35: "or by the earth, for it is his footstool; or by Jerusalem, for it is the city of the Great King.",
            36: "And do not swear by your head, for you cannot make even one hair white or black.",
            37: "All you need to say is simply 'Yes' or 'No'; otherwise you will be condemned.",
            38: "\"You have heard that it was said, 'Eye for eye, and tooth for tooth.'",
            39: "But I tell you, do not resist an evil person. If someone slaps you on one cheek, turn to them the other also.",
            40: "If someone wants to sue you and take your shirt, let them have your coat as well.",
            41: "If someone forces you to go one mile, go with them two miles.",
            42: "Give to the one who asks you, and do not turn away from the one who wants to borrow from you.",
            43: "\"You have heard that it was said, 'Love your neighbor and hate your enemy.'",
            44: "But I tell you, love your enemies and pray for those who persecute you,",
            45: "that you may be children of your Father in heaven. He causes his sun to rise on the evil and the good, and sends rain on the righteous and the unrighteous.",
            46: "If you love those who love you, what reward will you get? Are not even the tax collectors doing that?",
            47: "And if you greet only your own people, what are you doing more than others? Do not even pagans do that?",
            48: "Be perfect, therefore, as your heavenly Father is perfect."
        },
        6: {
            1: "\"Be careful not to practice your righteousness in front of others to be seen by them. If you do, you will have no reward from your Father in heaven.",
            2: "\"So when you give to the needy, do not announce it with trumpets, as the hypocrites do in the synagogues and on the streets, to be honored by others. Truly I tell you, they have received their reward in full.",
            3: "But when you give to the needy, do not let your left hand know what your right hand is doing,",
            4: "so that your giving may be in secret. Then your Father, who sees what is done in secret, will reward you.",
            5: "\"And when you pray, do not be like the hypocrites, for they love to pray standing in the synagogues and on the street corners to be seen by others. Truly I tell you, they have received their reward in full.",
            6: "But when you pray, go into your room, close the door and pray to your Father, who is unseen. Then your Father, who sees what is done in secret, will reward you.",
            7: "And when you pray, do not keep on babbling like pagans, for they think they will be heard because of their many words.",
            8: "Do not be like them, for your Father knows what you need before you ask him.",
            9: "\"This, then, is how you should pray: \"'Our Father in heaven, hallowed be your name,",
            10: "your kingdom come, your will be done, on earth as it is in heaven.",
            11: "Give us today our daily bread.",
            12: "And forgive us our debts, as we also have forgiven our debtors.",
            13: "And lead us not into temptation, but deliver us from the evil one.'",
            14: "For if you forgive other people when they sin against you, your heavenly Father will also forgive you.",
            15: "But if you do not forgive others their sins, your Father will not forgive your sins.",
            16: "\"When you fast, do not look somber as the hypocrites do, for they disfigure their faces to show others they are fasting. Truly I tell you, they have received their reward in full.",
            17: "But when you fast, put oil on your head and wash your face,",
            18: "so that it will not be obvious to others that you are fasting, but only to your Father, who is unseen; and your Father, who sees what is done in secret, will reward you.",
            19: "\"Do not store up for yourselves treasures on earth, where moths and vermin destroy, and where thieves break in and steal.",
            20: "But store up for yourselves treasures in heaven, where moths and vermin do not destroy, and where thieves do not break in and steal.",
            21: "For where your treasure is, there your heart will be also.",
            22: "\"The eye is the lamp of the body. If your eyes are healthy, your whole body will be full of light.",
            23: "But if your eyes are unhealthy, your whole body will be full of darkness. If then the light within you is darkness, how great is that darkness!",
            24: "\"No one can serve two masters. Either you will hate the one and love the other, or you will be devoted to the one and despise the other. You cannot serve both God and money.",
            25: "\"Therefore I tell you, do not worry about your life, what you will eat or drink; or about your body, what you will wear. Is not life more than food, and the body more than clothes?",
            26: "Look at the birds of the air; they do not sow or reap or store away in barns, and yet your heavenly Father feeds them. Are you not much more valuable than they?",
            27: "Can any one of you by worrying add a single hour to your life?",
            28: "\"And why do you worry about clothes? See how the flowers of the field grow. They do not labor or spin.",
            29: "Yet I tell you that not even Solomon in all his splendor was dressed like one of these.",
            30: "If that is how God clothes the grass of the field, which is here today and tomorrow is thrown into the fire, will he not much more clothe you—you of little faith?",
            31: "So do not worry, saying, 'What shall we eat?' or 'What shall we drink?' or 'What shall we wear?'",
            32: "For the pagans run after all these things, and your heavenly Father knows that you need them.",
            33: "But seek first his kingdom and his righteousness, and all these things will be given to you as well.",
            34: "Therefore do not worry about tomorrow, for tomorrow will worry about itself. Each day has enough trouble of its own."
        },
        7: {
            1: "\"Do not judge, or you too will be judged.",
            2: "For in the same way you judge others, you will be judged, and with the measure you use, it will be measured to you.",
            3: "\"Why do you look at the speck of sawdust in your brother's eye and pay no attention to the plank in your own eye?",
            4: "How can you say to your brother, 'Let me take the speck out of your eye,' when all the time there is a plank in your own eye?",
            5: "You hypocrite, first take the plank out of your own eye, and then you will see clearly to remove the speck from your brother's eye.",
            6: "\"Do not give dogs what is sacred; do not throw your pearls to pigs. If you do, they may trample them under their feet, and turn and tear you to pieces.",
            7: "\"Ask and it will be given to you; seek and you will find; knock and the door will be opened to you.",
            8: "For everyone who asks receives; the one who seeks finds; and to the one who knocks, the door will be opened.",
            9: "\"Which of you, if your son asks for bread, will give him a stone?",
            10: "Or if he asks for a fish, will give him a snake?",
            11: "If you, then, though you are evil, know how to give good gifts to your children, how much more will your Father in heaven give good gifts to those who ask him!",
            12: "So in everything, do to others what you would have them do to you, for this sums up the Law and the Prophets.",
            13: "\"Enter through the narrow gate. For wide is the gate and broad is the road that leads to destruction, and many enter through it.",
            14: "But small is the gate and narrow the road that leads to life, and only a few find it.",
            15: "\"Watch out for false prophets. They come to you in sheep's clothing, but inwardly they are ferocious wolves.",
            16: "By their fruit you will recognize them. Do people pick grapes from thornbushes, or figs from thistles?",
            17: "Likewise, every good tree bears good fruit, but a bad tree bears bad fruit.",
            18: "A good tree cannot bear bad fruit, and a bad tree cannot bear good fruit.",
            19: "Every tree that does not bear good fruit is cut down and thrown into the fire.",
            20: "Thus, by their fruit you will recognize them.",
            21: "\"Not everyone who says to me, 'Lord, Lord,' will enter the kingdom of heaven, but only the one who does the will of my Father who is in heaven.",
            22: "Many will say to me on that day, 'Lord, Lord, did we not prophesy in your name and in your name drive out demons and in your name perform many miracles?'",
            23: "Then I will tell them plainly, 'I never knew you. Away from me, you evildoers!'",
            24: "\"Therefore everyone who hears these words of mine and puts them into practice is like a wise man who built his house on the rock.",
            25: "The rain came down, the streams rose, and the winds blew and beat against that house; yet it did not fall, because it had its foundation on the rock.",
            26: "But everyone who hears these words of mine and does not put them into practice is like a foolish man who built his house on sand.",
            27: "The rain came down, the streams rose, and the winds blew and beat against that house, and it fell with a great crash.\"",
            28: "When Jesus had finished saying these things, the crowds were amazed at his teaching,",
            29: "because he taught as one who had authority, and not as their teachers of the law."
        },
        8: {
            1: "When Jesus came down from the mountainside, large crowds followed him.",
            2: "A man with leprosy came and knelt before him and said, \"Lord, if you are willing, you can make me clean.\"",
            3: "Jesus reached out his hand and touched the man. \"I am willing,\" he said. \"Be clean!\" Immediately he was cleansed of his leprosy.",
            4: "Then Jesus said to him, \"See that you don't tell anyone. But go, show yourself to the priest and offer the gift Moses commanded, as a testimony to them.\"",
            5: "When Jesus had entered Capernaum, a centurion came to him, asking for help.",
            6: "\"Lord,\" he said, \"my servant lies at home paralyzed, suffering terribly.\"",
            7: "Jesus said to him, \"Shall I come and heal him?\"",
            8: "The centurion replied, \"Lord, I do not deserve to have you come under my roof. But just say the word, and my servant will be healed.",
            9: "For I myself am a man under authority, with soldiers under me. I tell this one, 'Go,' and he goes; and that one, 'Come,' and he comes. I say to my servant, 'Do this,' and he does it.\"",
            10: "When Jesus heard this, he was amazed and said to those following him, \"Truly I tell you, I have not found anyone in Israel with such great faith.",
            11: "I say to you that many will come from the east and the west, and will take their places at the feast with Abraham, Isaac and Jacob in the kingdom of heaven.",
            12: "But the subjects of the kingdom will be thrown outside, into the darkness, where there will be weeping and gnashing of teeth.\"",
            13: "Then Jesus said to the centurion, \"Go! Let it be done just as you believed it would.\" And his servant was healed at that moment.",
            14: "When Jesus came into Peter's house, he saw Peter's mother-in-law lying in bed with a fever.",
            15: "He touched her hand and the fever left her, and she got up and began to wait on him.",
            16: "When evening came, many who were demon-possessed were brought to him, and he drove out the spirits with a word and healed all the sick.",
            17: "This was to fulfill what was spoken through the prophet Isaiah: \"He took up our infirmities and bore our diseases.\"",
            18: "When Jesus saw the crowd around him, he gave orders to cross to the other side of the lake.",
            19: "Then a teacher of the law came to him and said, \"Teacher, I will follow you wherever you go.\"",
            20: "Jesus replied, \"Foxes have dens and birds have nests, but the Son of Man has no place to lay his head.\"",
            21: "Another disciple said to him, \"Lord, first let me go and bury my father.\"",
            22: "But Jesus told him, \"Follow me, and let the dead bury their own dead.\"",
            23: "Then he got into the boat and his disciples followed him.",
            24: "Suddenly a furious storm came up on the lake, so that the waves swept over the boat. But Jesus was sleeping.",
            25: "The disciples went and woke him, saying, \"Lord, save us! We're going to drown!\"",
            26: "He replied, \"You of little faith, why are you so afraid?\" Then he got up and rebuked the winds and the waves, and it was completely calm.",
            27: "The men were amazed and asked, \"What kind of man is this? Even the winds and the waves obey him!\"",
            28: "When he arrived at the other side in the region of the Gadarenes, two demon-possessed men coming from the tombs met him. They were so violent that no one could pass that way.",
            29: "\"What do you want with us, Son of God?\" they shouted. \"Have you come here to torture us before the appointed time?\"",
            30: "Some distance from them a large herd of pigs was feeding.",
            31: "The demons begged Jesus, \"If you drive us out, send us into the herd of pigs.\"",
            32: "He said to them, \"Go!\" So they came out and went into the pigs, and the whole herd rushed down the steep bank into the lake and died in the water.",
            33: "Those tending the pigs ran off, went into the town and reported all this, including what had happened to the demon-possessed men.",
            34: "Then the whole town went out to meet Jesus. And when they saw him, they pleaded with him to leave their region."
        }
    }
}

# Hebrew (Transliterated) - Original language for Old Testament
BIBLE_HEBREW = {
    "Genesis": {
        1: {
            1: "בְּרֵאשִׁית בָּרָא אֱלֹהִים אֵת הַשָּׁמַיִם וְאֵת הָאָרֶץ.",
            2: "וְהָאָרֶץ הָיְתָה תֹהוּ וָבֹהוּ וְחֹשֶׁךְ עַל-פְּנֵי תְהוֹם וְרוּחַ אֱלֹהִים מְרַחֶפֶת עַל-פְּנֵי הַמָּיִם.",
            3: "וַיֹּאמֶר אֱלֹהִים יְהִי אוֹר וַיְהִי-אוֹר.",
            4: "וַיַּרְא אֱלֹהִים אֶת-הָאוֹר כִּי-טוֹב וַיַּבְדֵּל אֱלֹהִים בֵּין הָאוֹר וּבֵין הַחֹשֶׁךְ.",
            5: "וַיִּקְרָא אֱלֹהִים לָאוֹר יוֹם וְלַחֹשֶׁךְ קָרָא לָיְלָה וַיְהִי-עֶרֶב וַיְהִי-בֹקֶר יוֹם אֶחָד.",
            6: "וַיֹּאמֶר אֱלֹהִים יְהִי רָקִיעַ בְּתוֹךְ הַמָּיִם וִיהִי מַבְדִּיל בֵּין מַיִם לָמָיִם.",
            7: "וַיַּעַשׂ אֱלֹהִים אֶת-הָרָקִיעַ וַיַּבְדֵּל בֵּין הַמַּיִם אֲשֶׁר מִתַּחַת לָרָקִיעַ וּבֵין הַמַּיִם אֲשֶׁר מֵעַל לָרָקִיעַ וַיְהִי-כֵן.",
            8: "וַיִּקְרָא אֱלֹהִים לָרָקִיעַ שָׁמָיִם וַיְהִי-עֶרֶב וַיְהִי-בֹקֶר יוֹם שֵׁנִי.",
            9: "וַיֹּאמֶר אֱלֹהִים יִקָּווּ הַמַּיִם מִתַּחַת הַשָּׁמַיִם אֶל-מָקוֹם אֶחָד וְתֵרָאֶה הַיַּבָּשָׁה וַיְהִי-כֵן.",
            10: "וַיִּקְרָא אֱלֹהִים לַיַּבָּשָׁה אֶרֶץ וּלְמִקְוֵה הַמַּיִם קָרָא יַמִּים וַיַּרְא אֱלֹהִים כִּי-טוֹב."
        }
    },
    "Psalms": {
        23: {
            1: "מִזְמוֹר לְדָוִד יְהוָה רֹעִי לֹא אֶחְסָר.",
            2: "בִּנְאוֹת דֶּשֶׁא יַרְבִּיצֵנִי עַל-מֵי מְנֻחוֹת יְנַהֲלֵנִי.",
            3: "נַפְשִׁי יְשׁוֹבֵב יַנְחֵנִי בְּמַעְגְּלֵי-צֶדֶק לְמַעַן שְׁמוֹ.",
            4: "גַּם כִּי-אֵלֵךְ בְּגֵיא צַלְמָוֶת לֹא-אִירָא רָע כִּי-אַתָּה עִמָּדִי שִׁבְטְךָ וּמִשְׁעַנְתֶּךָ הֵמָּה יְנַחֲמֻנִי.",
            5: "תַּעֲרֹךְ לְפָנַי שֻׁלְחָן נֶגֶד צֹרְרָי דִּשַּׁנְתָּ בַשֶּׁמֶן רֹאשִׁי כּוֹסִי רְוָיָה.",
            6: "אַךְ טוֹב וָחֶסֶד יִרְדְּפוּנִי כָּל-יְמֵי חַיַּי וְשַׁבְתִּי בְּבֵית-יְהוָה לְאֹרֶךְ יָמִים."
        }
    },
    "Matthew": {
        1: {
            1: "סֵפֶר תּוֹלְדוֹת יֵשׁוּעַ הַמָּשִׁיחַ בֶּן-דָּוִד בֶּן-אַבְרָהָם.",
            2: "אַבְרָהָם הוֹלִיד אֶת-יִצְחָק וְיִצְחָק הוֹלִיד אֶת-יַעֲקֹב וְיַעֲקֹב הוֹלִיד אֶת-יְהוּדָה וְאֶת-אֶחָיו.",
            3: "וִיהוּדָה הוֹלִיד אֶת-פֶּרֶץ וְאֶת-זֶרַח מִתָּמָר וּפֶרֶץ הוֹלִיד אֶת-חֶצְרוֹן וְחֶצְרוֹן הוֹלִיד אֶת-רָם.",
            4: "וְרָם הוֹלִיד אֶת-עַמִּינָדָב וְעַמִּינָדָב הוֹלִיד אֶת-נַחְשׁוֹן וְנַחְשׁוֹן הוֹלִיד אֶת-סַלְמוֹן.",
            5: "וְסַלְמוֹן הוֹלִיד אֶת-בֹּעַז מֵרָחָב וּבֹעַז הוֹלִיד אֶת-עוֹבֵד מֵרוּת וְעוֹבֵד הוֹלִיד אֶת-יִשַׁי.",
            6: "וְיִשַּׁי הוֹלִיד אֶת-דָּוִד הַמֶּלֶךְ וְדָוִד הוֹלִיד אֶת-שְׁלֹמֹה מֵאֵשֶׁת אוּרִיָּה.",
            7: "וּשְׁלֹמֹה הוֹלִיד אֶת-רְחַבְעָם וְרְחַבְעָם הוֹלִיד אֶת-אֲבִיָּה וַאֲבִיָּה הוֹלִיד אֶת-אָסָא.",
            8: "וְאָסָא הוֹלִיד אֶת-יְהוֹשָׁפָט וִיהוֹשָׁפָט הוֹלִיד אֶת-יוֹרָם וְיוֹרָם הוֹלִיד אֶת-עֻזִּיָּהוּ.",
            9: "וְעֻזִּיָּהוּ הוֹלִיד אֶת-יוֹתָם וְיוֹתָם הוֹלִיד אֶת-אָחָז וְאָחָז הוֹלִיד אֶת-חִזְקִיָּהוּ.",
            10: "וְחִזְקִיָּהוּ הוֹלִיד אֶת-מְנַשֶּׁה וּמְנַשֶּׁה הוֹלִיד אֶת-אָמוֹן וְאָמוֹן הוֹלִיד אֶת-יֹאשִׁיָּהוּ.",
            11: "וְיֹאשִׁיָּהוּ הוֹלִיד אֶת-יְכָנְיָה וְאֶת-אֶחָיו בִּזְמַן גָּלוּת בָּבֶל.",
            12: "וְאַחֲרֵי גָּלוּת בָּבֶל יְכָנְיָה הוֹלִיד אֶת-שְׁאַלְתִּיאֵל וּשְׁאַלְתִּיאֵל הוֹלִיד אֶת-זְרֻבָּבֶל.",
            13: "וְזְרֻבָּבֶל הוֹלִיד אֶת-אֲבִיהוּד וַאֲבִיהוּד הוֹלִיד אֶת-אֶלְיָקִים וְאֶלְיָקִים הוֹלִיד אֶת-עָזוּר.",
            14: "וְעָזוּר הוֹלִיד אֶת-צָדוֹק וְצָדוֹק הוֹלִיד אֶת-יָכִין וְיָכִין הוֹלִיד אֶת-אֶלִיהוּד.",
            15: "וְאֶלִיהוּד הוֹלִיד אֶת-אֶלְעָזָר וְאֶלְעָזָר הוֹלִיד אֶת-מַתָּן וּמַתָּן הוֹלִיד אֶת-יַעֲקֹב.",
            16: "וְיַעֲקֹב הוֹלִיד אֶת-יוֹסֵף בַּעַל מִרְיָם אֲשֶׁר מִמֶּנָּה נוֹלַד יֵשׁוּעַ הַנִּקְרָא מָשִׁיחַ.",
            17: "כָּל הַדּוֹרוֹת מֵאַבְרָהָם עַד דָּוִד אַרְבָּעָה עָשָׂר דּוֹרוֹת וּמִדָּוִד עַד גָּלוּת בָּבֶל אַרְבָּעָה עָשָׂר דּוֹרוֹת וּמִגָּלוּת בָּבֶל עַד הַמָּשִׁיחַ אַרְבָּעָה עָשָׂר דּוֹרוֹת.",
            18: "וְהִנֵּה לֵידַת יֵשׁוּעַ הַמָּשִׁיחַ כָּךְ הָיָה כַּאֲשֶׁר מִרְיָם אִמּוֹ הָיְתָה מְאֹרֶשֶׂת לְיוֹסֵף לִפְנֵי שֶׁבָּאוּ יַחְדָּו נִמְצְאָה הָרָה מֵרוּחַ הַקֹּדֶשׁ.",
            19: "וְיוֹסֵף בַּעְלָהּ אִישׁ צַדִּיק הוּא וְלֹא רָצָה לְהוֹצִיאָהּ לְחֶרְפָּה וַיָּחְשֹׁב לְשַׁלְּחָהּ בַּסֵּתֶר.",
            20: "וְהוּא חוֹשֵׁב עַל אֵלֶּה וְהִנֵּה מַלְאַךְ יְהוָה נִרְאָה אֵלָיו בַּחֲלוֹם לֵאמֹר יוֹסֵף בֶּן-דָּוִד אַל-תִּירָא לָקַחַת אֶת-מִרְיָם אִשְׁתְּךָ כִּי הַהֵרָיוֹן אֲשֶׁר בָּהּ מֵרוּחַ הַקֹּדֶשׁ הוּא.",
            21: "וְהִיא תֵּלֵד בֵּן וְתִקְרָא אֶת-שְׁמוֹ יֵשׁוּעַ כִּי-הוּא יוֹשִׁיעַ אֶת-עַמּוֹ מֵחַטֹּאתֵיהֶם.",
            22: "וְכָל-זֹאת הָיְתָה לְמַלֵּא אֶת אֲשֶׁר דִּבֶּר יְהוָה בְּיַד הַנָּבִיא לֵאמֹר:",
            23: "הִנֵּה הָעַלְמָה הָרָה וְיֹלֶדֶת בֵּן וְקָרְאוּ שְׁמוֹ עִמָּנוּאֵל אֲשֶׁר פֵּרוּשׁוֹ אֵל עִמָּנוּ.",
            24: "וַיּוֹסֵף הֵקִיץ מִשְּׁנָתוֹ וַיַּעַשׂ כַּאֲשֶׁר צִוָּהוּ מַלְאַךְ יְהוָה וַיִּקַּח אֶת-אִשְׁתּוֹ.",
            25: "וְלֹא יָדְעָהּ עַד אֲשֶׁר יָלְדָה אֶת-בְּנָהּ הַבְּכוֹר וַיִּקְרָא אֶת-שְׁמוֹ יֵשׁוּעַ."
        },
        2: {
            1: "וַיֵּשׁוּעַ נוֹלַד בְּבֵית לֶחֶם בִּיהוּדָה בִּימֵי הוֹרְדוֹס הַמֶּלֶךְ, וְהִנֵּה חֲכָמִים מִמִּזְרָח בָּאוּ לִירוּשָׁלַיִם.",
            2: "וַיֹּאמְרוּ, אֵיפֹה הוּא הַנּוֹלָד מֶלֶךְ הַיְּהוּדִים? כִּי רָאִינוּ אֶת-כּוֹכָבוֹ בַּמִּזְרָח וּבָאנוּ לְהִשְׁתַּחֲווֹת לוֹ.",
            3: "וַיִּשְׁמַע הוֹרְדוֹס הַמֶּלֶךְ וַיִּבָּהֵל, וְכָל-יְרוּשָׁלַיִם עִמּוֹ.",
            4: "וַיֶּאֱסֹף אֶת-כָּל רָאשֵׁי הַכֹּהֲנִים וְסוֹפְרֵי הָעָם, וַיִּשְׁאַל אוֹתָם אֵיפֹה יִוָּלֵד הַמָּשִׁיחַ.",
            5: "וַיֹּאמְרוּ אֵלָיו, בְּבֵית לֶחֶם בִּיהוּדָה, כִּי כֵן כָּתוּב עַל-יְדֵי הַנָּבִיא.",
            6: "וְאַתָּה בֵּית לֶחֶם אֶרֶץ יְהוּדָה, לֹא צָעִיר אַתָּה בְּאַלְפֵי יְהוּדָה, כִּי מִמְּךָ יֵצֵא מוֹשֵׁל אֲשֶׁר יִרְעֶה אֶת-עַמִּי יִשְׂרָאֵל.",
            7: "אָז הוֹרְדוֹס קָרָא לַחֲכָמִים בַּסֵּתֶר, וַיִּדְרֹשׁ מֵהֶם אֶת-עֵת הַכּוֹכָב הַנִּרְאֶה.",
            8: "וַיִּשְׁלַחֵם לְבֵית לֶחֶם וַיֹּאמֶר, לְכוּ וְחַפְּשׂוּ הֵיטֵב אֶת-הַיֶּלֶד, וּכְשֶׁתִּמְצְאוּהוּ הַגִּידוּ לִי, לְמַעַן אָבוֹא גַּם אֲנִי לְהִשְׁתַּחֲווֹת לוֹ.",
            9: "וַיִּשְׁמְעוּ אֶת-הַמֶּלֶךְ וַיֵּלְכוּ, וְהִנֵּה הַכּוֹכָב אֲשֶׁר רָאוּ בַּמִּזְרָח הוֹלֵךְ לִפְנֵיהֶם עַד בּוֹאוֹ וַיַּעֲמֹד מֵעַל הַמָּקוֹם אֲשֶׁר הַיֶּלֶד שָׁם.",
            10: "וַיִּרְאוּ אֶת-הַכּוֹכָב וַיִּשְׂמְחוּ שִׂמְחָה גְּדוֹלָה מְאֹד.",
            11: "וַיָּבֹאוּ הַבַּיְתָה, וַיִּרְאוּ אֶת-הַיֶּלֶד עִם מִרְיָם אִמּוֹ, וַיִּפְּלוּ וַיִּשְׁתַּחֲווּ לוֹ, וַיִּפְתְּחוּ אֶת-אוֹצְרוֹתֵיהֶם וַיַּקְרִיבוּ לוֹ מַתָּנוֹת: זָהָב וּלְבוֹנָה וּמוֹר.",
            12: "וַיּוּזְהֲרוּ בַּחֲלוֹם שֶׁלֹּא לָשׁוּב אֶל-הוֹרְדוֹס, וַיָּשֻׁבוּ בְּדֶרֶךְ אַחֶרֶת אֶל-אַרְצָם.",
            13: "וַיֵּלְכוּ הֵם, וְהִנֵּה מַלְאַךְ יְהוָה נִרְאָה אֶל-יוֹסֵף בַּחֲלוֹם לֵאמֹר, קוּם קַח אֶת-הַיֶּלֶד וְאֶת-אִמּוֹ, וּבְרַח מִצְרַיְמָה, וֶהְיֵה שָׁם עַד אֲשֶׁר אֹמַר לְךָ, כִּי הוֹרְדוֹס מְבַקֵּשׁ אֶת-הַיֶּלֶד לְהַשְׁמִידוֹ.",
            14: "וַיָּקָם וַיִּקַּח אֶת-הַיֶּלֶד וְאֶת-אִמּוֹ לַיְלָה, וַיֵּלֶךְ מִצְרַיְמָה.",
            15: "וַיְהִי שָׁם עַד מוֹת הוֹרְדוֹס, לְמַעַן יִמָּלֵא הַדָּבָר הַנֶּאֱמָר מֵאֵת יְהוָה עַל-יַד הַנָּבִיא, מִמִּצְרַיִם קָרָאתִי לִבְנִי.",
            16: "אָז הוֹרְדוֹס כִּי רָאָה כִּי הוּטְעָה מִן-הַחֲכָמִים, וַיִּקְצֹף מְאֹד, וַיִּשְׁלַח וַיַּהֲרֹג אֶת-כָּל הַיְּלָדִים אֲשֶׁר בְּבֵית לֶחֶם וּבְכָל גְּבוּלֶיהָ, מִבֶּן שְׁנָתַיִם וּלְמַטָּה, כְּעֵת אֲשֶׁר חִקֵּר מֵאֵת הַחֲכָמִים.",
            17: "אָז נִמְלָא הַדָּבָר הַנֶּאֱמָר עַל-יְדֵי יִרְמְיָהוּ הַנָּבִיא לֵאמֹר,",
            18: "קוֹל בְּרָמָה נִשְׁמָע, נְהִי בְּכִי תַמְרוּרִים, רָחֵל מְבַכָּה עַל-בָּנֶיהָ, מֵאֲנָה לְהִנָּחֵם עַל-בָּנֶיהָ כִּי אֵינֶנּוּ.",
            19: "וַיְהִי אַחֲרֵי מוֹת הוֹרְדוֹס, וְהִנֵּה מַלְאַךְ יְהוָה נִרְאָה בַּחֲלוֹם אֶל-יוֹסֵף בְּמִצְרַיִם.",
            20: "וַיֹּאמֶר, קוּם קַח אֶת-הַיֶּלֶד וְאֶת-אִמּוֹ, וְלֵךְ אֶל-אֶרֶץ יִשְׂרָאֵל, כִּי מֵתוּ מְבַקְשֵׁי נֶפֶשׁ הַיֶּלֶד.",
            21: "וַיָּקָם וַיִּקַּח אֶת-הַיֶּלֶד וְאֶת-אִמּוֹ, וַיָּבוֹא אֶל-אֶרֶץ יִשְׂרָאֵל.",
            22: "וַיִּשְׁמַע כִּי אַרְכֵּלָאוֹס מֹלֵךְ בִּיהוּדָה תַּחַת הוֹרְדוֹס אָבִיו, וַיִּירָא לָלֶכֶת שָׁמָּה, וַיּוּזְהַר בַּחֲלוֹם, וַיָּסַר אֶל-גָּלִיל.",
            23: "וַיָּבוֹא וַיֵּשֶׁב בְּעִיר הַנִּקְרֵאת נָצְרַת, לְמַעַן יִמָּלֵא הַנֶּאֱמָר עַל-יְדֵי הַנְּבִיאִים, נָצְרִי יִקָּרֵא."
        },
        3: {
            1: "בַּיָּמִים הָהֵם בָּא יוֹחָנָן הַמַּטְבִּיל, קוֹרֵא בַּמִּדְבָּר יְהוּדָה,",
            2: "וְאוֹמֵר, שׁוּבוּ, כִּי קָרְבָה מַלְכוּת הַשָּׁמַיִם.",
            3: "כִּי זֶהוּ אֲשֶׁר דִּבֶּר עָלָיו יְשַׁעְיָהוּ הַנָּבִיא לֵאמֹר, קוֹל קוֹרֵא בַּמִּדְבָּר, פַּנוּ דֶּרֶךְ יְהוָה, יַשְּׁרוּ נְתִיבוֹתָיו.",
            4: "וְיוֹחָנָן הָיָה לָבוּשׁ שֵׂעָר גְּמַלִּים וְאֵזוֹר עוֹר בְּמוֹתְנָיו, וּמַאֲכָלוֹ אַרְבֶּה וּדְבַשׁ יַעַר.",
            5: "אָז יָצְאוּ אֵלָיו יְרוּשָׁלַיִם וְכָל-יְהוּדָה וְכָל כִּכַּר הַיַּרְדֵּן.",
            6: "וַיִּטְבְּלוּ בִּימֵי הַיַּרְדֵּן עַל-יָדָיו, מִתְוַדִּים עַל-חַטֹּאותֵיהֶם.",
            7: "וַיַּרְא רַבִּים מִן-הַפְּרוּשִׁים וְהַצְּדוּקִים בָּאִים אֶל-טְבִילָתוֹ, וַיֹּאמֶר לָהֶם, יַלְדֵּי נְחָשִׁים, מִי הִזְהִיר אֶתְכֶם לָנוּס מִן-הַחֵמָה הַבָּאָה?",
            8: "עֲשׂוּ פְּרִי רָאוּי לִתְשׁוּבָה.",
            9: "וְאַל-תַּחְשְׁבוּ לוֹמַר בְּנַפְשְׁכֶם, אָבִינוּ אַבְרָהָם. כִּי אוֹמֵר אֲנִי לָכֶם, כִּי יָכוֹל אֱלֹהִים לְהָקִים מִן-הָאֲבָנִים הָאֵלֶּה בָּנִים לְאַבְרָהָם.",
            10: "וְהִנֵּה הַגַּרְזֶן מוּסָם עַל-שֹׁרֶשׁ הָעֵצִים, וְכָל עֵץ אֲשֶׁר אֵינוֹ עֹשֶׂה פְּרִי טוֹב יִכָּרֵת וְיוּשְׁלַךְ בָּאֵשׁ.",
            11: "אֲנִי מַטְבִּיל אֶתְכֶם בַּמַּיִם לִתְשׁוּבָה, אֲבָל הַבָּא אַחֲרַי חָזָק מִמֶּנִּי, אֲשֶׁר לֹא שָׁוִיתִי לָשֵׂאת נַעֲלָיו. הוּא יַטְבִּיל אֶתְכֶם בְּרוּחַ הַקֹּדֶשׁ וּבָאֵשׁ.",
            12: "מִזְרְתוֹ בְיָדוֹ, וִיטַהֵר אֶת-גָּרְנוֹ, וְיֶאֱסֹף אֶת-חִטָּיו אֶל-הָאוֹצָר, וְאֶת-הַמֹּץ יִשְׂרֹף בָּאֵשׁ אֲשֶׁר לֹא תִכְבֶּה.",
            13: "אָז בָּא יֵשׁוּעַ מִן-הַגָּלִיל אֶל-הַיַּרְדֵּן אֶל-יוֹחָנָן לְהִטַּבֵּל עַל-יָדוֹ.",
            14: "וְיוֹחָנָן מָנַע מִמֶּנּוּ לֵאמֹר, אֲנִי צָרִיךְ לְהִטַּבֵּל עַל-יָדְךָ, וְאַתָּה בָּא אֵלַי?",
            15: "וַיַּעַן יֵשׁוּעַ וַיֹּאמֶר אֵלָיו, הַנַּח עַתָּה כִּי כֵן נָאֶה לָנוּ לְמַלֵּא אֶת-כָּל הַצְּדָקָה. אָז הִנִּיחַ לוֹ.",
            16: "וַיֵּשׁוּעַ נִטְבַּל וַיַּעַל מִיָּד מִן-הַמַּיִם, וְהִנֵּה נִפְתְּחוּ לוֹ הַשָּׁמַיִם, וַיַּרְא אֶת-רוּחַ אֱלֹהִים יוֹרֶדֶת כְּיוֹנָה וּבָאָה עָלָיו.",
            17: "וְהִנֵּה קוֹל מִן-הַשָּׁמַיִם אוֹמֵר, זֶה בְּנִי הָאָהוּב אֲשֶׁר בּוֹ חָפַצְתִּי."
        },
        4: {
            1: "אָז הוּבָל יֵשׁוּעַ עַל-יְדֵי הָרוּחַ הַקּוֹדֶשׁ אֶל-הַמִּדְבָּר לְהִתְנַסּוֹת עַל-יְדֵי הַשָּׂטָן.",
            2: "וַיָּצוּם אַרְבָּעִים יוֹם וְאַרְבָּעִים לַיְלָה, וְאַחֲרֵי כֵן רָעֵב.",
            3: "וַיִּגַּשׁ אֵלָיו הַמְּנַסֶּה וַיֹּאמֶר, אִם-בֶּן אֱלֹהִים אַתָּה, אֱמֹר לָאֲבָנִים הָאֵלֶּה שֶׁיִּהְיוּ לְלֶחֶם.",
            4: "וַיַּעַן יֵשׁוּעַ וַיֹּאמֶר, כָּתוּב: לֹא עַל הַלֶּחֶם לְבַדּוֹ יִחְיֶה הָאָדָם, כִּי עַל כָּל-דָּבָר יוֹצֵא מִפִּי יְהוָה.",
            5: "אָז לָקַח אֹתוֹ הַשָּׂטָן אֶל-הָעִיר הַקּוֹדֶשׁ, וַיַּעֲמִידֵהוּ עַל מִפְלַס הַהֵיכָל,",
            6: "וַיֹּאמֶר אֵלָיו, אִם-בֶּן אֱלֹהִים אַתָּה, הַשְׁלֵךְ אֶת-עַצְמְךָ מִטָּה, כִּי כָּתוּב: לְמַלְאָכָיו יְצַוֶּה עָלֶיךָ, וְעַל-כַּפַּיִם יִשָּׂאוּךָ, פֶּן-תִּגֹּף אֶת-רַגְלְךָ בְּאֶבֶן.",
            7: "אָמַר אֵלָיו יֵשׁוּעַ, גַּם כָּתוּב: לֹא תְנַסֶּה אֶת-יְהוָה אֱלֹהֶיךָ.",
            8: "שׁוּב לָקַח אֹתוֹ הַשָּׂטָן אֶל-הַר גָּבוֹהַּ מְאֹד, וַיַּרְאֵהוּ אֶת-כָּל מַמְלְכוֹת הָעוֹלָם וְאֶת-כְּבוֹדָן,",
            9: "וַיֹּאמֶר אֵלָיו, אֶת-כָּל-אֵלֶּה אֶתֵּן לְךָ, אִם-תִּפֹּל וְתִשְׁתַּחֲוֶה לִי.",
            10: "אָז אָמַר אֵלָיו יֵשׁוּעַ, לֵךְ מֵאִתִּי, הַשָּׂטָן, כִּי כָּתוּב: לַיהוָה אֱלֹהֶיךָ תִּשְׁתַּחֲוֶה, וְאוֹתוֹ לְבַדּוֹ תַּעֲבֹד.",
            11: "אָז עָזַב אֹתוֹ הַשָּׂטָן, וְהִנֵּה מַלְאָכִים נִגְּשׁוּ וְשֵׁרְתוּ אֹתוֹ.",
            12: "וַיִּשְׁמַע יֵשׁוּעַ כִּי יוֹחָנָן נִתְפַּס, וַיָּסַר אֶל-הַגָּלִיל.",
            13: "וַיַּעֲזֹב אֶת-נָצְרַת וַיָּבֹא וַיֵּשֶׁב בְּכַפַּר נַחוּם, אֲשֶׁר עַל-שְׂפַת יָם הַגָּלִיל, בִּגְבוּל זְבֻלוּן וְנַפְתָּלִי.",
            14: "לְמַעַן יִמָּלֵא הַדָּבָר הַנֶּאֱמָר עַל-יְדֵי יְשַׁעְיָהוּ הַנָּבִיא, לֵאמֹר:",
            15: "אֶרֶץ זְבֻלוּן וְאֶרֶץ נַפְתָּלִי, דֶּרֶךְ הַיָּם, מֵעֵבֶר לַיַּרְדֵּן, גָּלִיל הַגּוֹיִם.",
            16: "הָעָם הַיּוֹשֵׁב בַּחֹשֶׁךְ רָאָה אוֹר גָּדוֹל, וְלַיּוֹשְׁבִים בְּאֶרֶץ צֵל מָוֶת אוֹר זָרַח עֲלֵיהֶם.",
            17: "מֵאוֹתָהּ שָׁעָה הֵחֵל יֵשׁוּעַ לְהַכְרִיז וְלֹאמַר, שׁוּבוּ מֵחַטֹּאתֵיכֶם, כִּי מַלְכוּת הַשָּׁמַיִם קָרְבָה.",
            18: "וַיֵּלֶךְ יֵשׁוּעַ עַל-שְׂפַת יָם הַגָּלִיל, וַיַּרְא שְׁנֵי אַחִים, שִׁמְעוֹן הַנִּקְרָא פֶּטְרוֹס וְאַנְדְּרֵי אָחִיו, מַשְׁלִיכִים מִכְמֹרֶת בַּיָּם, כִּי דַיָּגִים הָיוּ.",
            19: "וַיֹּאמֶר אֲלֵיהֶם, בֹּאוּ אַחֲרַי, וְאֶעֱשֶׂה אֶתְכֶם דַּיָּגֵי אָדָם.",
            20: "וַיַּעֲזְבוּ מִיָּד אֶת-הַמִּכְמֹרוֹת וַיֵּלְכוּ אַחֲרָיו.",
            21: "וַיֵּלֶךְ מִשָּׁם, וַיַּרְא שְׁנֵי אַחִים אֲחֵרִים, יַעֲקֹב בֶּן-זְבַדְיָה וְיוֹחָנָן אָחִיו, בַּסְּפִינָה עִם זְבַדְיָה אֲבִיהֶם, מְתַקְנִים אֶת-מִכְמְרוֹתֵיהֶם, וַיִּקְרָא לָהֶם.",
            22: "וַיַּעֲזְבוּ מִיָּד אֶת-הַסְּפִינָה וְאֶת-אֲבִיהֶם וַיֵּלְכוּ אַחֲרָיו.",
            23: "וַיָּסַר יֵשׁוּעַ בְּכָל-הַגָּלִיל, מְלַמֵּד בְּבָתֵּי כְנֵסִיּוֹתֵיהֶם וּמַכְרִיז אֶת-בְּשׂוֹרַת מַלְכוּת הַשָּׁמַיִם, וּמְרַפֵּא כָּל-חֹלִי וְכָל-מַחֲלָה בָּעָם.",
            24: "וַיֵּלֶךְ שְׁמַעְתּוֹ בְּכָל-סוּרְיָה, וַיָּבִיאוּ אֵלָיו אֶת-כָּל-הַחוֹלִים, אֲשֶׁר נֶאֱנָסִים בְּחֳלָיִים שׁוֹנִים וּבְכָאֲבִים, וּשְׁדוּפִים, וְיָרְחִים, וּנְכֵה יָדַיִם וְרַגְלַיִם, וַיִּרְפָּאֵם.",
            25: "וַיֵּלְכוּ אַחֲרָיו הֲמוֹנִים רַבִּים מֵהַגָּלִיל וּמִדְּקַפּוֹלִיס וּמִירוּשָׁלַיִם וּמִיהוּדָה וּמֵעֵבֶר לַיַּרְדֵּן."
        },
        5: {
            1: "וַיַּרְא יֵשׁוּעַ אֶת-הֲמוֹנִים וַיַּעַל אֶל-הָהָר וַיֵּשֶׁב שָׁם וַיִּגַּשׁוּ אֵלָיו תַּלְמִידָיו.",
            2: "וַיִּפְתַּח אֶת-פִּיו וַיְלַמְּדֵם לֵאמֹר:",
            3: "אַשְׁרֵי עֲנִיֵי הָרוּחַ כִּי לָהֶם מַלְכוּת הַשָּׁמַיִם.",
            4: "אַשְׁרֵי הָאֲבֵלִים כִּי הֵם יְנֻחָמוּ.",
            5: "אַשְׁרֵי הָעֲנָוִים כִּי הֵם יִירְשׁוּ אֶת-הָאָרֶץ.",
            6: "אַשְׁרֵי הָרְעֵבִים וְהַצְּמֵאִים לַצְּדָקָה כִּי הֵם יִשְׂבָּעוּ.",
            7: "אַשְׁרֵי הָרַחֲמָנִים כִּי הֵם יְרֻחָמוּ.",
            8: "אַשְׁרֵי טְהוֹרֵי הַלֵּב כִּי הֵם יִרְאוּ אֶת-הָאֱלֹהִים.",
            9: "אַשְׁרֵי רוֹדְפֵי הַשָּׁלוֹם כִּי בָנִים לֵאלֹהִים יִקָּרְאוּ.",
            10: "אַשְׁרֵי הַנִּרְדָּפִים בַּעֲבוּר הַצְּדָקָה כִּי לָהֶם מַלְכוּת הַשָּׁמַיִם.",
            11: "אַשְׁרֵי אַתֶּם כִּי יְחָרְפוּ אֶתְכֶם וְיִרְדְּפוּ אֶתְכֶם וְיֹאמְרוּ עֲלֵיכֶם כָּל-דָּבָר רָע בִּשְׁקָר בַּעֲבוּרִי.",
            12: "שִׂמְחוּ וְגִילוּ כִּי שְׂכַרְכֶם רָב בַּשָּׁמַיִם כִּי כֵן רָדְפוּ אֶת-הַנְּבִיאִים אֲשֶׁר לִפְנֵיכֶם.",
            13: "אַתֶּם מֶלַח הָאָרֶץ וְאִם-יִפְסַד הַמֶּלַח אֵיךְ יִמְלַח אַחֵר? לֹא יוֹעִיל עוֹד לִמְאוּמָה כִּי אִם-לְהִשָּׁלֵךְ חוּצָה וְלִרְמֹס תַּחַת רַגְלֵי הָאָדָם.",
            14: "אַתֶּם אוֹר הָעוֹלָם עִיר שֶׁעַל-הַר לֹא תוּכַל לְהִסָּתֵר.",
            15: "וְלֹא מַדְלִיקִים נֵר וְשָׂמִים אוֹתוֹ תַּחַת הָאֵיפָה כִּי אִם-עַל הַמְּנוֹרָה וְהוּא מֵאִיר לְכָל-אֲשֶׁר בַּבַּיִת.",
            16: "כֵּן יָאֵר אוֹרְכֶם לִפְנֵי הָאָדָם לְמַעַן יִרְאוּ מַעֲשֵׂיכֶם הַטּוֹבִים וִיהַלְלוּ אֶת-אֲבִיכֶם אֲשֶׁר בַּשָּׁמַיִם.",
            17: "אַל-תַּחְשְׁבוּ כִּי בָאתִי לְהָפֵר אֶת-הַתּוֹרָה אוֹ אֶת-הַנְּבִיאִים לֹא בָאתִי לְהָפֵר כִּי אִם-לְמַלֵּא.",
            18: "כִּי אָמֵן אֹמֵר אֲנִי לָכֶם עַד אֲשֶׁר-יַעַבְרוּ הַשָּׁמַיִם וְהָאָרֶץ לֹא-יַעֲבֹר יוֹד אֶחָד אוֹ קֶרֶן אַחַת מִן-הַתּוֹרָה עַד אֲשֶׁר יִהְיֶה הַכֹּל.",
            19: "לָכֵן כָּל-מִי שֶׁיָּפֵר אַחַת מִן-הַמִּצְוֹת הַקְּטַנּוֹת הָאֵלֶּה וִילַמֵּד כֵן אֶת-הָאָדָם קָטָן יִקָּרֵא בְּמַלְכוּת הַשָּׁמַיִם וְכָל-מִי שֶׁיַּעֲשֶׂה וִילַמֵּד גָּדוֹל יִקָּרֵא בְּמַלְכוּת הַשָּׁמַיִם.",
            20: "כִּי אֹמֵר אֲנִי לָכֶם כִּי אִם-לֹא תִרְבֶּה צִדְקוּתְכֶם מִצִּדְקוּת הַסּוֹפְרִים וְהַפְּרוּשִׁים לֹא תָבֹאוּ בְּשֶׁלֶם אֶל-מַלְכוּת הַשָּׁמַיִם.",
            21: "שְׁמַעְתֶּם כִּי נֶאֱמַר לָאָבוֹת הָרִאשׁוֹנִים לֹא תִרְצָח וְכָל-הָרוֹצֵחַ יִהְיֶה חַיָּב לַמִּשְׁפָּט.",
            22: "וַאֲנִי אֹמֵר לָכֶם כָּל-מִי שֶׁיִּכְעַס עַל-אָחִיו יִהְיֶה חַיָּב לַמִּשְׁפָּט וְכָל-מִי שֶׁיֹּאמַר לְאָחִיו רֵיקָא יִהְיֶה חַיָּב לְסַנְהֶדְרִין וְכָל-מִי שֶׁיֹּאמַר כְּסִיל יִהְיֶה חַיָּב לְאֵשׁ גֵּיהִנֹּם.",
            23: "לָכֵן אִם-תָּבִיא קָרְבָּנְךָ אֶל-הַמִּזְבֵּחַ וְשָׁם תִּזְכֹּר כִּי אָחִיךָ יֵשׁ לוֹ מַשֶּׁהוּ עָלֶיךָ.",
            24: "הַנַּח שָׁם אֶת-קָרְבָּנְךָ לִפְנֵי הַמִּזְבֵּחַ וְלֵךְ תְּחִלָּה וְהִתְרַצֶּה עִם-אָחִיךָ וְאַחַר תָּבֹא וְהַקְרֵב אֶת-קָרְבָּנְךָ.",
            25: "הִתְרַצֶּה מַהֵר עִם-יְרִיבְךָ בְּעוֹדְךָ עִמּוֹ בַּדֶּרֶךְ פֶּן-יַסְגִּירְךָ הַיָּרִיב לַשּׁוֹפֵט וְהַשּׁוֹפֵט יַסְגִּירְךָ לַמִּשְׁמָר וְתִשָּׁלֵךְ לַכֶּלֶא.",
            26: "אָמֵן אֹמֵר אֲנִי לְךָ לֹא תֵצֵא מִשָּׁם עַד אֲשֶׁר תְּשַׁלֵּם אֶת-הַלַּסְטָר הָאַחֲרוֹן.",
            27: "שְׁמַעְתֶּם כִּי נֶאֱמַר לֹא תִנְאָף.",
            28: "וַאֲנִי אֹמֵר לָכֶם כָּל-מִי שֶׁיַּבִּיט אֶל-אִשָּׁה לְתַאֲוָה כְּבָר נִאֵף עִמָּהּ בְּלִבּוֹ.",
            29: "וְאִם-עֵינְךָ הַיְּמָנִית מַכְשִׁילָה אוֹתְךָ עֲקֹר אוֹתָהּ וְהַשְׁלֵךְ מִמְּךָ כִּי טוֹב לְךָ שֶׁיֹּאבַד אֵבֶר אֶחָד מִגּוּפְךָ וְלֹא כָל-גּוּפְךָ יִשָּׁלֵךְ לְגֵיהִנֹּם.",
            30: "וְאִם-יָדְךָ הַיְּמָנִית מַכְשִׁילָה אוֹתְךָ קְצֹץ אוֹתָהּ וְהַשְׁלֵךְ מִמְּךָ כִּי טוֹב לְךָ שֶׁיֹּאבַד אֵבֶר אֶחָד מִגּוּפְךָ וְלֹא כָל-גּוּפְךָ יֵלֵךְ לְגֵיהִנֹּם.",
            31: "וְנֶאֱמַר כָּל-הַמְשַׁלֵּחַ אֶת-אִשְׁתּוֹ יִתֵּן לָהּ סֵפֶר כְּרִיתוּת.",
            32: "וַאֲנִי אֹמֵר לָכֶם כָּל-מִי שֶׁיְשַׁלֵּחַ אֶת-אִשְׁתּוֹ לְלֹא עֲלִילַת זְנוּת יַעֲשֶׂה אוֹתָהּ לְזוֹנָה וְכָל-מִי שֶׁיִּשָּׂא אִשָּׁה גְּרוּשָׁה יִנְאָף.",
            33: "עוֹד שְׁמַעְתֶּם כִּי נֶאֱמַר לָאָבוֹת הָרִאשׁוֹנִים לֹא תִשָּׁבַע בִּשְׁקָר וְתְשַׁלֵּם לַיהוָה אֶת-נְדָרֶיךָ.",
            34: "וַאֲנִי אֹמֵר לָכֶם לֹא תִשָּׁבְעוּ כָל-עִקָּר לֹא בַשָּׁמַיִם כִּי כִסֵּא אֱלֹהִים הֵם.",
            35: "וְלֹא בָאָרֶץ כִּי הֲדֹם רַגְלָיו וְלֹא בִירוּשָׁלַיִם כִּי עִיר הַמֶּלֶךְ הַגָּדוֹל הִיא.",
            36: "וְלֹא בְרֹאשְׁךָ תִשָּׁבַע כִּי לֹא תוּכַל לַעֲשׂוֹת שֵׂעָר אֶחָד לָבָן אוֹ שָׁחוֹר.",
            37: "יְהִי דְבַרְכֶם כֵּן כֵּן לֹא לֹא וּמַה שֶׁיִּתְרֶה עַל-אֵלֶּה מֵהָרָע הוּא.",
            38: "שְׁמַעְתֶּם כִּי נֶאֱמַר עַיִן תַּחַת עַיִן וְשֶׁנֶּה תַּחַת שֶׁנֶּה.",
            39: "וַאֲנִי אֹמֵר לָכֶם לֹא תָּמִידוּ לָרָע אֶלָּא אִם-יַכֶּה אוֹתְךָ מִישֶׁהוּ עַל-הַלֶּחִי הַיְּמָנִית הָפֵן אֵלָיו גַם אֶת-הַשְּׁנִיָּה.",
            40: "וְלַמִּי שֶׁיִּרְצֶה לִשָּׁפְטְךָ וְלָקַחַת אֶת-כֻּתָּנְתְּךָ הַנַּח לוֹ גַם אֶת-הַמְּעִיל.",
            41: "וְלַמִּי שֶׁיַּכְרִיחַ אוֹתְךָ לָלֶכֶת מִיל אֶחָד לֵךְ עִמּוֹ שְׁנַיִם.",
            42: "לַמִּי שֶׁשּׁוֹאֵל מֵאִתְּךָ תֵּן לוֹ וְלַמִּי שֶׁיִּרְצֶה לָלוֹת מִמְּךָ אַל-תָּסֵב מִמֶּנּוּ.",
            43: "שְׁמַעְתֶּם כִּי נֶאֱמַר אֱהַב אֶת-רֵעֲךָ וְשָׂנֵא אֶת-אוֹיִבְךָ.",
            44: "וַאֲנִי אֹמֵר לָכֶם אֱהַבוּ אֶת-אוֹיְבֵיכֶם וְהִתְפַּלְלוּ בְּעַד הָרוֹדְפִים אֶתְכֶם.",
            45: "לְמַעַן תִּהְיוּ בָנִים לַאֲבִיכֶם אֲשֶׁר בַּשָּׁמַיִם כִּי הוּא מַעֲלֶה שִׁמְשׁוֹ עַל-רָעִים וְטוֹבִים וּמַמְטִיר עַל-צַדִּיקִים וְעַל-רְשָׁעִים.",
            46: "כִּי אִם-תֶּאֱהֲבוּ אֶת-אֹהֲבֵיכֶם מָה-שְׂכָרְכֶם? הֲלֹא גַם הַמּוֹכְסִים עוֹשִׂים כֵן?",
            47: "וְאִם-תְּבָרְכוּ רַק אֶת-אֲחֵיכֶם מָה-יִתְרוֹן לָכֶם? הֲלֹא גַם הַגּוֹיִים עוֹשִׂים כֵן?",
            48: "לָכֵן הֱיוּ שְׁלֵמִים כְּשֶׁלֵם אֲבִיכֶם אֲשֶׁר בַּשָּׁמַיִם."
        },
        6: {
            1: "הִשָּׁמְרוּ לְבִלְתִּי עֲשׂוֹת צִדְקוּתְכֶם לִפְנֵי הָאָדָם לְמַעַן הֵרָאוֹת לָהֶם כִּי אִם-לֹא תִהְיֶה לָכֶם שְׂכָר מֵאֵת אֲבִיכֶם אֲשֶׁר בַּשָּׁמַיִם.",
            2: "לָכֵן כַּאֲשֶׁר תִּתֵּן צְדָקָה אַל-תְּרַעֵשׁ בְּשׁוֹפָר לְפָנֶיךָ כַּאֲשֶׁר עוֹשִׂים הַצְּבוּעִים בַּבָּתִּים וּבַשְּׁוָקִים לְמַעַן יְהַלְלוּ אוֹתָם הָאָדָם אָמֵן אֹמֵר אֲנִי לָכֶם קִבְּלוּ שְׂכָרָם בְּמָלֵא.",
            3: "וְאַתָּה בְּתִתְּךָ צְדָקָה אַל-יֵדַע שְׂמֹאלְךָ מַה-שֶּׁיַּעֲשֶׂה יְמִינֶךָ.",
            4: "לְמַעַן תִּהְיֶה צְדָקָתְךָ בַסֵּתֶר וַאֲבִיךָ הָרֹאֶה בַסֵּתֶר יְשַׁלֵּם לָךְ.",
            5: "וּכְשֶׁתִּתְפַּלֵּל אַל-תִּהְיֶה כַּצְּבוּעִים כִּי אָהֲבוּ לְהִתְפַּלֵּל עוֹמְדִים בַּבָּתִּים וּבְפִנּוֹת הָרְחֹבוֹת לְמַעַן הֵרָאוֹת לָאָדָם אָמֵן אֹמֵר אֲנִי לָכֶם קִבְּלוּ שְׂכָרָם בְּמָלֵא.",
            6: "וְאַתָּה בְּהִתְפַּלְּלֶךָ בֹּא אֶל-חֶדְרְךָ וְסָגֹר דְּלָתְךָ וְהִתְפַּלֵּל אֶל-אָבִיךָ אֲשֶׁר בַּסֵּתֶר וַאֲבִיךָ הָרֹאֶה בַסֵּתֶר יְשַׁלֵּם לָךְ.",
            7: "וּבְהִתְפַּלְּלְכֶם אַל-תַּשְׁנּוּ כַּגּוֹיִים כִּי יַחְשְׁבוּ בְּרֹב דִּבְרֵיהֶם יִשָּׁמְעוּ.",
            8: "אַל-תִּדְמּוּ לָהֶם כִּי יוֹדֵעַ אֲבִיכֶם מַה-צָּרְכְכֶם בְּטֶרֶם תִּשְׁאֲלוּ מֵאִתּוֹ.",
            9: "לָכֵן כָּךְ תִּתְפַּלְּלוּ אַתֶּם אָבִינוּ שֶׁבַּשָּׁמַיִם יִתְקַדֵּשׁ שִׁמְךָ.",
            10: "תָּבוֹא מַלְכוּתְךָ יֵעָשֶׂה רְצוֹנְךָ כַּאֲשֶׁר בַּשָּׁמַיִם כֵּן בָּאָרֶץ.",
            11: "אֶת-לֶחֶם חֻקֵּנוּ תֵּן-לָנוּ הַיּוֹם.",
            12: "וְסָלַח לָנוּ אֶת-חוֹבוֹתֵינוּ כַּאֲשֶׁר סָלַחְנוּ גַם-אֲנַחְנוּ לְחַיָּבֵינוּ.",
            13: "וְאַל-תְּבִיאֵנוּ לִידֵי נִסָּיוֹן כִּי אִם-הַצִּילֵנוּ מִן-הָרָע.",
            14: "כִּי אִם-תִּסְלְחוּ לָאָדָם אֶת-פִּשְׁעֵיהֶם יִסְלַח לָכֶם גַם-אֲבִיכֶם שֶׁבַּשָּׁמַיִם.",
            15: "וְאִם לֹא תִסְלְחוּ לָאָדָם אֶת-פִּשְׁעֵיהֶם גַּם-אֲבִיכֶם לֹא יִסְלַח לָכֶם אֶת-פִּשְׁעֵיכֶם.",
            16: "וּכְשֶׁתָּצוּמוּ אַל-תִּהְיוּ קוֹדְרִים כַּצְּבוּעִים כִּי יְשַׁחֲתוּ פְנֵיהֶם לְמַעַן יֵרָאוּ לָאָדָם צוֹמִים אָמֵן אֹמֵר אֲנִי לָכֶם קִבְּלוּ שְׂכָרָם בְּמָלֵא.",
            17: "וְאַתָּה בְּצָמְךָ מְשַׁח אֶת-רֹאשְׁךָ וְרַחֵץ פָּנֶיךָ.",
            18: "לְמַעַן לֹא תֵרָאֶה לָאָדָם צוֹם כִּי אִם-לְאָבִיךָ אֲשֶׁר בַּסֵּתֶר וַאֲבִיךָ הָרֹאֶה בַסֵּתֶר יְשַׁלֵּם לָךְ.",
            19: "אַל-תִּצְבְּרוּ לָכֶם אוֹצָרוֹת בָּאָרֶץ אֲשֶׁר עָשׁ וְרִמָּה מַשְׁחִיתִים וַאֲשֶׁר גַּנָּבִים חוֹפְרִים וְגוֹנְבִים.",
            20: "כִּי אִם-צִבְּרוּ לָכֶם אוֹצָרוֹת בַּשָּׁמַיִם אֲשֶׁר לֹא עָשׁ וְלֹא רִמָּה מַשְׁחִיתִים וְלֹא גַּנָּבִים חוֹפְרִים וְגוֹנְבִים.",
            21: "כִּי אֲשֶׁר יִהְיֶה אוֹצָרְךָ שָׁם יִהְיֶה לִבְּךָ גַם-הוּא.",
            22: "נֵר הַגּוּף הוּא הָעַיִן אִם-יִהְיֶה עֵינְךָ טוֹב יָאִיר כָּל-גּוּפְךָ.",
            23: "וְאִם-יִהְיֶה עֵינְךָ רָעָה יֶחְשַׁךְ כָּל-גּוּפְךָ וְאִם-אֵפוֹא הָאוֹר אֲשֶׁר בְּךָ חֹשֶׁךְ מַה-גָּדוֹל הַחֹשֶׁךְ.",
            24: "אֵין אִישׁ יָכוֹל לַעֲבֹד שְׁנֵי אֲדוֹנִים כִּי אִם-יִשְׂנָא אֶת-הָאֶחָד וְיֶאֱהַב אֶת-הַשֵּׁנִי אוֹ יִדְבַּק בָּאֶחָד וְיִבְזֶה אֶת-הַשֵּׁנִי לֹא תוּכְלוּ לַעֲבֹד אֱלֹהִים וּמָמוֹן.",
            25: "לָכֵן אֹמֵר אֲנִי לָכֶם אַל-תִּדְאֲגוּ לְנַפְשְׁכֶם מַה-תֹּאכְלוּ וּמַה-תִּשְׁתּוּ וְלֹא לְגוּפְכֶם מַה-תִּלְבָּשׁוּ הֲלֹא הַנֶּפֶשׁ יְקָרָה מִן-הָאֹכֶל וְהַגּוּף מִן-הַלְּבוּשׁ.",
            26: "הַבִּיטוּ אֶל-עוֹף הַשָּׁמַיִם כִּי לֹא יִזְרְעוּ וְלֹא יִקְצְרוּ וְלֹא יֶאֱסְפוּ אֶל-אֲסַמִּים וַאֲבִיכֶם שֶׁבַּשָּׁמַיִם מְכַלְכְּלָם הֲלֹא אַתֶּם יְקָרִים מֵהֶם מְאֹד.",
            27: "וּמִי מִכֶּם בְּדָאֲגוֹ יוּכַל לְהוֹסִיף עַל-חַיָּיו אַמָּה אַחַת.",
            28: "וְלָמָּה תִדְאֲגוּ עַל-לְבוּשׁ רְאוּ אֶת-שׁוֹשַׁנּוֹת הַשָּׂדֶה אֵיךְ יִגְדָּלוּ לֹא יַעֲמִלוּ וְלֹא יִטּוּוּ.",
            29: "וְאוּלָם אֹמֵר אֲנִי לָכֶם כִּי גַם-שְׁלֹמֹה בְּכָל-כְּבוֹדוֹ לֹא לָבַשׁ כְּאַחַת מֵהֵנָּה.",
            30: "וְאִם אֶת-חֲצִיר הַשָּׂדֶה אֲשֶׁר הַיּוֹם יֵשׁ וּמָחָר יִשָּׁלֵךְ אֶל-הַתַּנּוּר כָּךְ יַלְבִּישׁ הָאֱלֹהִים אַף כִּי אַתֶּם קְטַנֵּי אֱמוּנָה.",
            31: "לָכֵן אַל-תִּדְאֲגוּ לֵאמֹר מַה-נֹּאכַל אוֹ מַה-נִּשְׁתֶּה אוֹ מַה-נִלְבַּשׁ.",
            32: "כִּי אֶת-כָּל-אֵלֶּה יְבַקְשׁוּ הַגּוֹיִים וַאֲבִיכֶם שֶׁבַּשָּׁמַיִם יוֹדֵעַ כִּי צְרִיכִים אַתֶּם לְכָל-אֵלֶּה.",
            33: "כִּי אִם-בַּקְשׁוּ תְּחִלָּה אֶת-מַלְכוּתוֹ וְצִדְקוֹ וְכָל-אֵלֶּה יִוָּסְפוּ לָכֶם.",
            34: "לָכֵן אַל-תִּדְאֲגוּ לַמָּחָר כִּי הַמָּחָר יִדְאַג לְעַצְמוֹ דַי לַיּוֹם רָעָתוֹ."
        },
        7: {
            1: "אַל-תִּשְׁפְּטוּ לְמַעַן לֹא תִשָּׁפְטוּ.",
            2: "כִּי בַּמִּשְׁפָּט אֲשֶׁר תִּשְׁפְּטוּ יִשָּׁפְטוּ אֶתְכֶם וּבַמִּדָּה אֲשֶׁר תְּמַדְּדוּ יְמַדְּדוּ לָכֶם.",
            3: "וּמַדּוּעַ תַּבִּיט אֶל-הַקֶּשֶׁת בְּעֵין אָחִיךָ וְהַקּוֹרָה בְעֵינְךָ לֹא תְבִינֶנָּה.",
            4: "אוֹ אֵיךְ תֹּאמַר לְאָחִיךָ הַנַּחֵנִי אַעֲשֶׂה אֶת-הַקֶּשֶׁת מֵעֵינְךָ וְהִנֵּה הַקּוֹרָה בְעֵינְךָ.",
            5: "צָבוּעַ הוֹצֵא תְּחִלָּה אֶת-הַקּוֹרָה מֵעֵינְךָ וְאַחַר תִּרְאֶה לְהוֹצִיא אֶת-הַקֶּשֶׁת מֵעֵין אָחִיךָ.",
            6: "אַל-תִּתְּנוּ אֶת-הַקֹּדֶשׁ לַכְּלָבִים וְאַל-תַּשְׁלִיכוּ מַרְגְּלִיתוֹתֵיכֶם לִפְנֵי הַחֲזִירִים פֶּן-יִרְמְסוּ אוֹתָם בְּרַגְלֵיהֶם וְיִפְנוּ וְיִקְרְעוּ אֶתְכֶם.",
            7: "שַׁאֲלוּ וְיִנָּתֵן לָכֶם בַּקְשׁוּ וְתִמְצָאוּ דַּפְּקוּ וְיִפָּתַח לָכֶם.",
            8: "כִּי כָל-הַשּׁוֹאֵל יִקַּח וְהַמְבַקֵּשׁ יִמְצָא וְלַדּוֹפֵק יִפָּתַח.",
            9: "מִי מִכֶּם אִישׁ אֲשֶׁר יִתֵּן לִבְנוֹ אֶבֶן אִם-יִשְׁאַל לֶחֶם.",
            10: "אוֹ אִם-יִשְׁאַל דָּג יִתֵּן לוֹ נָחָשׁ.",
            11: "אִם-אֵפוֹא אַתֶּם רָעִים יוֹדְעִים לָתֵת מַתָּנוֹת טוֹבוֹת לִבְנֵיכֶם כַּמָּה יוֹתֵר אֲבִיכֶם שֶׁבַּשָּׁמַיִם יִתֵּן טוֹבוֹת לַשּׁוֹאֲלִים מֵאִתּוֹ.",
            12: "לָכֵן כָּל אֲשֶׁר תַּחְפְּצוּ שֶׁיַּעֲשׂוּ לָכֶם הָאָדָם כֵּן עֲשׂוּ אַתֶּם לָהֶם כִּי זֶה הַתּוֹרָה וְהַנְּבִיאִים.",
            13: "בֹּאוּ בַשַּׁעַר הַצָּר כִּי רָחָב הַשַּׁעַר וּרְחָבָה הַדֶּרֶךְ הַמּוֹלִיכָה לָאֲבַדּוֹן וְרַבִּים הַבָּאִים בָּהּ.",
            14: "מַה-צָּר הַשַּׁעַר וּמַה-לְחוּצָה הַדֶּרֶךְ הַמּוֹלִיכָה לַחַיִּים וּמְעַטִּים הַמּוֹצְאִים אוֹתָהּ.",
            15: "הִשָּׁמְרוּ מִן-הַנְּבִיאִים הַשְּׁקָרִים הַבָּאִים אֵלֵיכֶם בִּלְבוּשׁ צֹאן וּמִבִּפְנִים זְאֵבִים טוֹרְפִים.",
            16: "מִפִּרְיָם תַּכִּירוּ אוֹתָם הַיִקְטֹפוּ עֲנָבִים מִן-הַקּוֹצִים אוֹ תְאֵנִים מִן-הַחֲרֻלִים.",
            17: "כֵּן כָּל-עֵץ טוֹב עוֹשֶׂה פְּרִי טוֹב וְעֵץ רַע עוֹשֶׂה פְּרִי רַע.",
            18: "לֹא יוּכַל עֵץ טוֹב לַעֲשׂוֹת פְּרִי רַע וְעֵץ רַע לַעֲשׂוֹת פְּרִי טוֹב.",
            19: "כָּל-עֵץ אֲשֶׁר לֹא-יַעֲשֶׂה פְּרִי טוֹב יִגָּדַע וְיִשָּׁלֵךְ אֶל-הָאֵשׁ.",
            20: "לָכֵן מִפִּרְיָם תַּכִּירוּ אוֹתָם.",
            21: "לֹא כָל-הָאוֹמֵר אֵלַי אֲדוֹנִי אֲדוֹנִי יָבוֹא אֶל-מַלְכוּת הַשָּׁמַיִם כִּי אִם-הָעוֹשֶׂה רְצוֹן אָבִי אֲשֶׁר בַּשָּׁמַיִם.",
            22: "רַבִּים יֹאמְרוּ אֵלַי בַּיּוֹם הַהוּא אֲדוֹנִי אֲדוֹנִי הֲלֹא בִשְׁמְךָ נִבֵּאנוּ וּבִשְׁמְךָ גֵרַשְׁנוּ שֵׁדִים וּבִשְׁמְךָ עָשִׂינוּ נִפְלָאוֹת רַבּוֹת.",
            23: "וְאָז אֹמַר אֲלֵיהֶם בְּגָלוּי לֹא יָדַעְתִּי אֶתְכֶם סוּרוּ מִמֶּנִּי פֹּעֲלֵי הָאָוֶן.",
            24: "לָכֵן כָּל-הַשּׁוֹמֵעַ אֶת-דְּבָרַי אֵלֶּה וְעוֹשֶׂה אוֹתָם יִדְמֶה לְאִישׁ חָכָם אֲשֶׁר בָּנָה בֵיתוֹ עַל-הַסֶּלַע.",
            25: "וַיֵּרֶד הַגֶּשֶׁם וַיָּבֹאוּ הַנְּהָרוֹת וַיִּשְּׁבוּ הָרוּחוֹת וַיִּפְגְּעוּ בַּבַּיִת הַהוּא וְלֹא נָפַל כִּי הָיָה יְסוּדוֹ עַל-הַסֶּלַע.",
            26: "וְכָל-הַשּׁוֹמֵעַ אֶת-דְּבָרַי אֵלֶּה וְלֹא עוֹשֶׂה אוֹתָם יִדְמֶה לְאִישׁ סָכָל אֲשֶׁר בָּנָה בֵיתוֹ עַל-הַחוֹל.",
            27: "וַיֵּרֶד הַגֶּשֶׁם וַיָּבֹאוּ הַנְּהָרוֹת וַיִּשְּׁבוּ הָרוּחוֹת וַיִּפְגְּעוּ בַּבַּיִת הַהוּא וַיִּפֹּל וַיְהִי מַפַּלְתּוֹ גְדוֹלָה.",
            28: "וַיְהִי כַּאֲשֶׁר כִּלָּה יֵשׁוּעַ אֶת-הַדְּבָרִים הָאֵלֶּה וַיִּתְמְהוּ הֲמוֹנִים עַל-תּוֹרָתוֹ.",
            29: "כִּי הָיָה מְלַמֵּד אוֹתָם כְּבַעַל סַמְכוּת וְלֹא כְּסוֹפְרֵיהֶם."
        },
        8: {
            1: "וּכְשֶׁיָּרַד יֵשׁוּעַ מִן-הָהָר וַיֵּלְכוּ אַחֲרָיו הֲמוֹנִים רַבִּים.",
            2: "וְהִנֵּה אִישׁ מְצוֹרָע בָּא וַיִּשְׁתַּחוּ לְפָנָיו לֵאמֹר אֲדוֹנִי אִם-תַּחְפֹּץ תּוּכַל לְטַהֲרֵנִי.",
            3: "וַיִּשְׁלַח יֵשׁוּעַ אֶת-יָדוֹ וַיִּגַּע בּוֹ לֵאמֹר אֲנִי חָפֵץ הֱיֵה טָהוֹר וּמִיָּד נִטְהַר מִצָּרַעְתּוֹ.",
            4: "וַיֹּאמֶר אֵלָיו יֵשׁוּעַ רְאֵה אַל-תַּגִּיד לְאִישׁ כִּי אִם-לֵךְ הֵרְאֵה אֶת-עַצְמְךָ לַכֹּהֵן וְהַקְרֵב אֶת-הַקָּרְבָּן אֲשֶׁר צִוָּה מֹשֶׁה לְעֵדוּת לָהֶם.",
            5: "וּכְבוֹא יֵשׁוּעַ אֶל-כַּפַּרְנַחוּם נִגַּשׁ אֵלָיו קֶנֶטְרִיּוֹן מְבַקֵּשׁ מִמֶּנּוּ.",
            6: "וַיֹּאמֶר אֲדוֹנִי עַבְדִּי שׁוֹכֵב בַּבַּיִת מְשַׁתַּק וְכוֹאֵב מְאֹד.",
            7: "וַיֹּאמֶר לוֹ יֵשׁוּעַ הֲאָבוֹא וְאֶרְפָּאֵהוּ.",
            8: "וַיַּעַן הַקֶּנֶטְרִיּוֹן וַיֹּאמֶר אֲדוֹנִי אֵינֶנִּי רָאוּי שֶׁתָּבוֹא תַּחַת גַּגִּי כִּי אִם-רַק אֱמֹר בִּדְבָר וְיֵרָפֵא עַבְדִּי.",
            9: "כִּי גַם-אֲנִי אִישׁ אָנֹכִי תַּחַת רָשׁוּת וַיֵּשׁ לִי חַיָּלִים תַּחְתָּי וְאֹמֵר לָזֶה לֵךְ וְהוֹלֵךְ וְלָזֶה בֹּא וּבָא וְלְעַבְדִּי עֲשֵׂה זֹאת וְעוֹשֶׂה.",
            10: "וַיִּשְׁמַע יֵשׁוּעַ וַיִּתְמַהּ וַיֹּאמֶר לַהֹלְכִים אַחֲרָיו אָמֵן אֹמֵר אֲנִי לָכֶם לֹא מָצָאתִי אֱמוּנָה כָּזֹאת בְּיִשְׂרָאֵל.",
            11: "וְאֹמֵר אֲנִי לָכֶם כִּי רַבִּים יָבוֹאוּ מִמִּזְרָח וּמִמַּעֲרָב וְיִשְׁבוּ עִם אַבְרָהָם וְיִצְחָק וְיַעֲקֹב בְּמַלְכוּת הַשָּׁמַיִם.",
            12: "וּבְנֵי הַמַּלְכוּת יִגָּרְשׁוּ אֶל-הַחֹשֶׁךְ הַחִיצוֹן שָׁם יִהְיֶה הַבְּכִי וְחַרְקַת הַשִּׁנַּיִם.",
            13: "וַיֹּאמֶר יֵשׁוּעַ לַקֶּנֶטְרִיּוֹן לֵךְ וְכַאֲשֶׁר הֶאֱמַנְתָּ יִהְיֶה לָךְ וַיֵּרָפֵא עַבְדּוֹ בָּעֵת הַהִיא.",
            14: "וַיָּבֹא יֵשׁוּעַ אֶל-בֵּית כֵּיפָא וַיַּרְא אֶת-חֲמוֹתוֹ שׁוֹכֶבֶת וְחוֹלָה בַקַּדַּחַת.",
            15: "וַיִּגַּע בְּיָדָהּ וַתַּעֲזֹב אוֹתָהּ הַקַּדַּחַת וַתָּקָם וַתְּשָׁרְתֵהוּ.",
            16: "וּכְעֶרֶב הָיָה וַיָּבִיאוּ אֵלָיו רַבִּים אֲחוּזֵי שֵׁדִים וַיְגָרֵשׁ אֶת-הָרוּחוֹת בִּדְבָר וַיִּרְפָּא אֶת-כָּל-הַחוֹלִים.",
            17: "לְמַעַן יִמָּלֵא הַנֶּאֱמָר עַל-יַד יְשַׁעְיָהוּ הַנָּבִיא לֵאמֹר הוּא נָשָׂא חֳלָיֵנוּ וְנָשָׂא מַכְאוֹבֵינוּ.",
            18: "וַיַּרְא יֵשׁוּעַ הֲמוֹנִים רַבִּים סְבִיבוֹתָיו וַיְצַו לַעֲבֹר אֶל-הָעֵבֶר הָאַחֵר.",
            19: "וַיִּגַּשׁ אֵלָיו סוֹפֵר אֶחָד וַיֹּאמֶר רַבִּי אֵלֵךְ אַחֲרֶיךָ בְּכָל אֲשֶׁר תֵּלֵךְ.",
            20: "וַיֹּאמֶר לוֹ יֵשׁוּעַ לַשּׁוּעָלִים חֹרִים וְלְעוֹפוֹת הַשָּׁמַיִם קִנִּים וְלִבֶן-הָאָדָם אֵין מָקוֹם אֲשֶׁר יַנִּיחַ אֶת-רֹאשׁוֹ.",
            21: "וַאֲחֵר מִתַּלְמִידָיו אָמַר לוֹ אֲדוֹנִי הַנַּח לִי תְּחִלָּה לָלֶכֶת וְלִקְבֹּר אֶת-אָבִי.",
            22: "וַיֹּאמֶר לוֹ יֵשׁוּעַ לֵךְ אַחֲרַי וְהַנַּח לַמֵּתִים לִקְבֹּר אֶת-מֵתֵיהֶם.",
            23: "וַיַּעַל אֶל-הַסְּפִינָה וַיֵּלְכוּ אַחֲרָיו תַּלְמִידָיו.",
            24: "וְהִנֵּה סַעַר גָּדוֹל נִהְיָה בַיָּם עַד אֲשֶׁר הַסְּפִינָה נִכְסְתָה מִן-הַגַּלִּים וְהוּא יָשֵׁן.",
            25: "וַיִּגַּשׁוּ תַּלְמִידָיו וַיְעִירוּהוּ לֵאמֹר אֲדוֹנִי הוֹשִׁיעֵנוּ אָנוּ אֹבְדִים.",
            26: "וַיֹּאמֶר לָהֶם מַה-תִּירְאוּ קְטַנֵּי אֱמוּנָה וַיָּקָם וַיְגַעַר בָּרוּחוֹת וּבַיָּם וַיְהִי שָׁלוֹם גָּדוֹל.",
            27: "וַיִּתְמְהוּ הָאֲנָשִׁים וַיֹּאמְרוּ מָה-זֶּה כִּי גַם-הָרוּחוֹת וְהַיָּם מִשְׁמָעִים לוֹ.",
            28: "וּכְבוֹאוֹ אֶל-הָעֵבֶר הָאַחֵר אֶל-אֶרֶץ הַגְּדָרִים נִפְגְּשׁוּ אִתּוֹ שְׁנַיִם אֲחוּזֵי שֵׁדִים יוֹצְאִים מִן-הַקְּבָרִים עַזִּים מְאֹד עַד אֲשֶׁר לֹא-יָכוֹל אִישׁ לַעֲבֹר בַּדֶּרֶךְ הַהוּא.",
            29: "וְהִנֵּה צָעֲקוּ לֵאמֹר מַה-לָּנוּ וָלָךְ בֶּן-הָאֱלֹהִים הֲבָאתָ לְהַכְעִיסֵנוּ לִפְנֵי הָעֵת.",
            30: "וְהָיָה מֵרָחוֹק מֵהֶם עֵדֶר חֲזִירִים רַבִּים רוֹעִים.",
            31: "וַיִּתְחַנְּנוּ אֵלָיו הַשֵּׁדִים לֵאמֹר אִם-תְּגָרֵשׁ אוֹתָנוּ שַׁלְּחֵנוּ אֶל-עֵדֶר הַחֲזִירִים.",
            32: "וַיֹּאמֶר לָהֶם לְכוּ וַיֵּצְאוּ וַיָּבֹאוּ אֶל-הַחֲזִירִים וְהִנֵּה נָהַר כָּל-הָעֵדֶר בַּמּוֹרָד אֶל-הַיָּם וַיָּמֻתוּ בַמַּיִם.",
            33: "וַיָּנֻסוּ הָרוֹעִים וַיָּבֹאוּ אֶל-הָעִיר וַיְסַפְּרוּ אֶת-הַכֹּל וְאֵת אֲשֶׁר קָרָה לַאֲחוּזֵי הַשֵּׁדִים.",
            34: "וְהִנֵּה כָל-הָעִיר יָצְאָה לִקְרַאת יֵשׁוּעַ וּכְרָאוֹתָם אוֹתוֹ בִקְּשׁוּ מִמֶּנּוּ לֵלֶךְ מִגְּבוּלָם."
        }
    }
}

# Greek (Transliterated) - Original language for New Testament  
BIBLE_GREEK = {
    "Matthew": {
        1: {
            1: "Biblos geneseōs Iēsou Christou huiou Dauid huiou Abraam.",
            2: "Abraam egennēsen ton Isaak, Isaak de egennēsen ton Iakōb, Iakōb de egennēsen ton Ioudan kai tous adelphous autou,",
            3: "Ioudas de egennēsen ton Phares kai ton Zara ek tēs Thamar, Phares de egennēsen ton Esrōm, Esrōm de egennēsen ton Aram,",
            4: "Aram de egennēsen ton Aminadab, Aminadab de egennēsen ton Naassōn, Naassōn de egennēsen ton Salmōn,",
            5: "Salmōn de egennēsen ton Boes ek tēs Rachab, Boes de egennēsen ton Iōbēd ek tēs Routh, Iōbēd de egennēsen ton Iessai,",
            6: "Iessai de egennēsen ton Dauid ton basilea. Dauid de egennēsen ton Solomōna ek tēs tou Ouriou,",
            7: "Solomōn de egennēsen ton Roboam, Roboam de egennēsen ton Abia, Abia de egennēsen ton Asaph,",
            8: "Asaph de egennēsen ton Iōsaphat, Iōsaphat de egennēsen ton Iōram, Iōram de egennēsen ton Ozian,",
            9: "Ozias de egennēsen ton Iōatham, Iōatham de egennēsen ton Achaz, Achaz de egennēsen ton Ezekian,",
            10: "Ezekias de egennēsen ton Manassē, Manassēs de egennēsen ton Amōs, Amōs de egennēsen ton Iōsian,",
            11: "Iōsias de egennēsen ton Iechonian kai tous adelphous autou epi tēs metoikesias Babylōnos.",
            12: "Meta de tēn metoikesian Babylōnos Iechonias egennēsen ton Salathiēl, Salathiēl de egennēsen ton Zorobabel,",
            13: "Zorobabel de egennēsen ton Abioud, Abioud de egennēsen ton Eliakim, Eliakim de egennēsen ton Azōr,",
            14: "Azōr de egennēsen ton Sadōk, Sadōk de egennēsen ton Achim, Achim de egennēsen ton Elioud,",
            15: "Elioud de egennēsen ton Eleazar, Eleazar de egennēsen ton Matthan, Matthan de egennēsen ton Iakōb,",
            16: "Iakōb de egennēsen ton Iōsēph ton andra Marias, ex hēs egennēthē Iēsous ho legomenos Christos.",
            17: "Pasai oun hai geneai apo Abraam heōs Dauid geneai dekatessares, kai apo Dauid heōs tēs metoikesias Babylōnos geneai dekatessares, kai apo tēs metoikesias Babylōnos heōs tou Christou geneai dekatessares.",
            18: "Tou de Iēsou Christou hē genesis houtōs ēn. Mnēsteutheisēs tēs mētros autou Marias tō Iōsēph, prin ē synelthein autous heurethē en gastri echousa ek Pneumatos Hagiou.",
            19: "Iōsēph de ho anēr autēs, dikaios ōn kai mē thelōn autēn deigmatisai, eboulēthē lathra apolusai autēn.",
            20: "Tauta de autou enthumēthentos idou angelos Kyriou kat' onar ephanē autō legōn, Iōsēph huios Dauid, mē phobēthēs paralabein Marian tēn gynaika sou; to gar en autē gennēthen ek Pneumatos estin Hagiou.",
            21: "Texetai de huion kai kaleseis to onoma autou Iēsoun; autos gar sōsei ton laon autou apo tōn hamartiōn autōn.",
            22: "Touto de holon gegonen hina plērōthē to rhēthen hypo Kyriou dia tou prophētou legontos,",
            23: "Idou hē parthenos en gastri hexei kai texetai huion, kai kalesousin to onoma autou Emmanouēl, ho estin methermēneuomenon Meth' hēmōn ho Theos.",
            24: "Egertheis de ho Iōsēph apo tou hypnou epoiēsen hōs prosetaxen autō ho angelos Kyriou kai parelaben tēn gynaika autou,",
            25: "Kai ouk eginōsken autēn heōs hou eteken huion; kai ekalesen to onoma autou Iēsoun."
        },
        2: {
            1: "Tou de Iēsou gennēthentos en Bēthleem tēs Ioudaias en hēmerais Hērōdou tou basileōs, idou magoi apo anatolōn paregenonto eis Hierosolyma",
            2: "legontes, Pou estin ho techtheis basileus tōn Ioudaiōn? eidomen gar autou ton astera en tē anatolē kai ēlthomen proskunēsai autō.",
            3: "Akousas de ho basileus Hērōdēs etarachthē kai pasa Hierosolyma met' autou,",
            4: "kai synagagōn pantas tous archiereis kai grammateis tou laou epynthaneto par' autōn pou ho Christos gennatai.",
            5: "Hoi de eipan autō, En Bēthleem tēs Ioudaias; houtōs gar gegraptai dia tou prophētou;",
            6: "Kai su Bēthleem, gē Iouda, oudamōs elachistē ei en tois hēgemosin Iouda; ek sou gar exeleusetai hēgoumenos, hostis poimanei ton laon mou ton Israēl.",
            7: "Tote Hērōdēs lathra kalesas tous magous ēkribōsen par' autōn ton chronon tou phainomenou asteros,",
            8: "kai pempsas autous eis Bēthleem eipen, Poreuthentes exetasate akribōs peri tou paidiou; epan de heurēte, apangeilate moi, hopōs kagō elthōn proskunēsō autō.",
            9: "Hoi de akousantes tou basileōs eporeuthēsan; kai idou ho astēr, hon eidon en tē anatolē, proēgen autous, heōs elthōn estathē epanō hou ēn to paidion.",
            10: "Idontes de ton astera echarēsan charan megalēn sphodra.",
            11: "Kai elthontes eis tēn oikian eidon to paidion meta Marias tēs mētros autou, kai pesontes prosekunēsan autō, kai anoixantes tous thēsaurous autōn prosēnenkan autō dōra, chruson kai libanon kai smurnan.",
            12: "Kai chrēmatisthentes kat' onar mē anakampsai pros Hērōdēn, di' allēs hodou anechōrēsan eis tēn chōran autōn.",
            13: "Anachōrēsantōn de autōn, idou angelos Kyriou phainetai kat' onar tō Iōsēph legōn, Egertheis paralabe to paidion kai tēn mētera autou kai pheuge eis Aigupton, kai isthi ekei heōs an eipō soi; mellei gar Hērōdēs zētein to paidion tou apolesai auto.",
            14: "Ho de egertheis parelaben to paidion kai tēn mētera autou nuktos kai anechōrēsen eis Aigupton,",
            15: "kai ēn ekei heōs tēs teleutēs Hērōdou; hina plērōthē to rhēthen hypo Kyriou dia tou prophētou legontos, Ex Aiguptou ekalesa ton huion mou.",
            16: "Tote Hērōdēs idōn hoti enepaixthē hypo tōn magōn ethumōthē lian, kai aposteilas aneilon pantas tous paidas tous en Bēthleem kai en pasi tois horiois autēs apo dietous kai katōterō, kata ton chronon hon ēkribōsen para tōn magōn.",
            17: "Tote eplērōthē to rhēthen dia Ieremiou tou prophētou legontos,",
            18: "Phōnē en Rhama ēkousthē, klauthmos kai odurmos polus, Rhachēl klaiousa ta tekna autēs, kai ouk ēthelen paraklēthēnai, hoti ouk eisin.",
            19: "Teleutēsantos de tou Hērōdou, idou angelos Kyriou phainetai kat' onar tō Iōsēph en Aiguptō",
            20: "legōn, Egertheis paralabe to paidion kai tēn mētera autou kai poreuou eis gēn Israēl; tethnēkasin gar hoi zētountes tēn psychēn tou paidiou.",
            21: "Ho de egertheis parelaben to paidion kai tēn mētera autou kai eisēlthen eis gēn Israēl.",
            22: "Akousas de hoti Archelaos basileuei tēs Ioudaias anti tou patros autou Hērōdou ephobēthē ekei apelthein; chrēmatistheis de kat' onar anechōrēsen eis ta merē tēs Galilaias,",
            23: "kai elthōn katōkēsen eis polin legomenēn Nazaret; hopōs plērōthē to rhēthen dia tōn prophētōn hoti Nazōraios klēthēsetai."
        },
        3: {
            1: "En de tais hēmerais ekeinais paraginetai Iōannēs ho Baptistēs kēryssōn en tē erēmō tēs Ioudaias",
            2: "kai legōn, Metanoeite; ēngiken gar hē basileia tōn ouranōn.",
            3: "Houtos gar estin ho rhētheis dia Ēsaiou tou prophētou legontos, Phōnē boōntos en tē erēmō, Hetoimasate tēn hodon Kyriou, eutheias poieite tas tribous autou.",
            4: "Autos de ho Iōannēs eichen to endyma autou apo trichōn kamēlou kai zōnēn dermatinēn peri tēn osphyn autou; hē de trophē ēn autou akrides kai meli agrion.",
            5: "Tote exeporeueto pros auton Hierosolyma kai pasa hē Ioudaia kai pasa hē perichōros tou Iordanou,",
            6: "kai ebaptizonto en tō Iordanē potamō hyp' autou exomologoumenoi tas hamartias autōn.",
            7: "Idōn de pollous tōn Pharisaiōn kai Saddoukaiōn erchomenous epi to baptisma autou eipen autois, Gennēmata echidnōn, tis hypedeixen hymin phygein apo tēs mellousēs orgēs?",
            8: "Poiēsate oun karpon axion tēs metanoias;",
            9: "kai mē doxēte legein en heautois, Patera echomen ton Abraam. Legō gar hymin hoti dynatai ho Theos ek tōn lithōn toutōn egeirai tekna tō Abraam.",
            10: "Ēdē de hē axinē pros tēn rhizan tōn dendrōn keitai; pan oun dendron mē poioun karpon kalon ekkoptetai kai eis pyr balletai.",
            11: "Egō men hymas baptizō en hydati eis metanoian; ho de opisō mou erchomenos ischyroteros mou estin, hou ouk eimi hikanos ta hypodēmata bastasai; autos hymas baptisei en Pneumati Hagiō kai pyri;",
            12: "hou to ptyon en tē cheiri autou, kai diakathariei tēn halōna autou, kai synaxei ton siton autou eis tēn apothēkēn, to de achyron katakausei pyri asbestō.",
            13: "Tote paraginetai ho Iēsous apo tēs Galilaias epi ton Iordanēn pros ton Iōannēn tou baptisthēnai hyp' autou.",
            14: "Ho de Iōannēs diekōlyen auton legōn, Egō chreian echō hypo sou baptisthēnai, kai sy erchē pros me?",
            15: "Apokritheis de ho Iēsous eipen pros auton, Aphes arti; houtōs gar prepon estin hēmin plērōsai pasan dikaiosynēn. Tote aphiēsin auton.",
            16: "Baptistheis de ho Iēsous euthys anebē apo tou hydatos; kai idou ēneōchthēsan autō hoi ouranoi, kai eiden to Pneuma tou Theou katabainon hōsei peristeran kai erchomenon ep' auton;",
            17: "kai idou phōnē ek tōn ouranōn legousa, Houtos estin ho Huios mou ho agapētos, en hō eudokēsa."
        }
    },
    "John": {
        1: {
            1: "En archē ēn ho Logos, kai ho Logos ēn pros ton Theon, kai Theos ēn ho Logos.",
            2: "Houtos ēn en archē pros ton Theon.",
            3: "Panta di' autou egeneto, kai chōris autou egeneto oude hen ho gegonen.",
            4: "En autō zōē ēn, kai hē zōē ēn to phōs tōn anthrōpōn.",
            5: "Kai to phōs en tē skotia phainei, kai hē skotia auto ou katelaben.",
            6: "Egeneto anthrōpos apestalmenos para Theou, onoma autō Iōannēs.",
            7: "Houtos ēlthen eis martyrian, hina martyrēsē peri tou phōtos, hina pantes pisteusōsin di' autou.",
            8: "Ouk ēn ekeinos to phōs, all' hina martyrēsē peri tou phōtos.",
            9: "Ēn to phōs to alēthinon, ho phōtizei panta anthrōpon, erchomenon eis ton kosmon.",
            10: "En tō kosmō ēn, kai ho kosmos di' autou egeneto, kai ho kosmos auton ouk egnō.",
            11: "Eis ta idia ēlthen, kai hoi idioi auton ou parelabon.",
            12: "Hosoi de elabon auton, edōken autois exousian tekna Theou genesthai, tois pisteuousin eis to onoma autou.",
            13: "Hoi ouk ex haimatōn oude ek thelēmatos sarkos oude ek thelēmatos andros all' ek Theou egennēthēsan.",
            14: "Kai ho Logos sarx egeneto kai eskēnōsen en hēmin, kai etheasametha tēn doxan autou, doxan hōs monogenous para Patros, plērēs charitos kai alētheias."
        },
        3: {
            16: "Houtōs gar ēgapēsen ho Theos ton kosmon, hōste ton Huion ton monogenē edōken, hina pas ho pisteuōn eis auton mē apolētai all' echē zōēn aiōnion.",
            17: "Ou gar apesteilen ho Theos ton Huion eis ton kosmon hina krinē ton kosmon, all' hina sōthē ho kosmos di' autou."
        }
    }
}

# ESV - English Standard Version
BIBLE_ESV = {
    "Genesis": {
        1: {
            1: "In the beginning, God created the heavens and the earth.",
            2: "The earth was without form and void, and darkness was over the face of the deep. And the Spirit of God was hovering over the face of the waters.",
            3: "And God said, \"Let there be light,\" and there was light.",
            4: "And God saw that the light was good. And God separated the light from the darkness.",
            5: "God called the light Day, and the darkness he called Night. And there was evening and there was morning, the first day."
        }
    },
    "John": {
        1: {
            1: "In the beginning was the Word, and the Word was with God, and the Word was God.",
            2: "He was in the beginning with God.",
            3: "All things were made through him, and without him was not any thing made that was made.",
            4: "In him was life, and the life was the light of men.",
            5: "The light shines in the darkness, and the darkness has not overcome it."
        },
        3: {
            16: "For God so loved the world, that he gave his only Son, that whoever believes in him should not perish but have eternal life.",
            17: "For God did not send his Son into the world to condemn the world, but in order that the world might be saved through him."
        }
    },
    "Psalms": {
        23: {
            1: "The LORD is my shepherd; I shall not want.",
            2: "He makes me lie down in green pastures. He leads me beside still waters.",
            3: "He restores my soul. He leads me in paths of righteousness for his name's sake.",
            4: "Even though I walk through the valley of the shadow of death, I will fear no evil, for you are with me; your rod and your staff, they comfort me.",
            5: "You prepare a table before me in the presence of my enemies; you anoint my head with oil; my cup overflows.",
            6: "Surely goodness and mercy shall follow me all the days of my life, and I shall dwell in the house of the LORD forever."
        }
    }
}

# NASB - New American Standard Bible
BIBLE_NASB = {
    "Genesis": {
        1: {
            1: "In the beginning God created the heavens and the earth.",
            2: "And the earth was formless and void, and darkness was over the surface of the deep; and the Spirit of God was moving over the surface of the waters.",
            3: "Then God said, \"Let there be light\"; and there was light.",
            4: "And God saw that the light was good; and God separated the light from the darkness.",
            5: "And God called the light day, and the darkness He called night. And there was evening and there was morning, one day."
        }
    },
    "John": {
        1: {
            1: "In the beginning was the Word, and the Word was with God, and the Word was God.",
            2: "He was in the beginning with God.",
            3: "All things came into being through Him, and apart from Him nothing came into being that has come into being.",
            4: "In Him was life, and the life was the Light of men.",
            5: "And the Light shines in the darkness, and the darkness did not comprehend it."
        },
        3: {
            16: "For God so loved the world, that He gave His only begotten Son, that whoever believes in Him shall not perish, but have eternal life.",
            17: "For God did not send the Son into the world to judge the world, but that the world might be saved through Him."
        }
    },
    "Psalms": {
        23: {
            1: "The LORD is my shepherd, I shall not want.",
            2: "He makes me lie down in green pastures; He leads me beside quiet waters.",
            3: "He restores my soul; He guides me in the paths of righteousness For His name's sake.",
            4: "Even though I walk through the valley of the shadow of death, I fear no evil, for You are with me; Your rod and Your staff, they comfort me.",
            5: "You prepare a table before me in the presence of my enemies; You have anointed my head with oil; My cup overflows.",
            6: "Surely goodness and lovingkindness will follow me all the days of my life, And I will dwell in the house of the LORD forever."
        }
    }
}

# Map translation codes to data
BIBLE_TRANSLATIONS = {
    "NIV": BIBLE_NIV,
    "Hebrew": BIBLE_HEBREW
}

# Primary Bible data (NIV as default)
BIBLE_DATA = BIBLE_NIV

# RITDorg YouTube Playlists by Book
# Official playlists from https://www.youtube.com/@RITDorg/playlists
RITDORG_PLAYLISTS = {
    # Old Testament
    "Genesis": "PL501265A092B62498",
    "Exodus": "PL6E830BE8B022CE3F",
    "Leviticus": "PL1CFCF7E4BF7FC645",
    "Numbers": "PL0C9F97EC36A1D7F6",
    "Deuteronomy": "PL8E1BF07B5EC9D83D",
    "Joshua": "PL91E6F08F6ABE60D6",
    "Judges": "PL19F42A4A3F2F1E0A",
    "Ruth": "PL3F48D70A0892C6CC",
    "1 Samuel": "PLD1E6C54A9C5E65E1",
    "2 Samuel": "PL4DAA88D08B5F71B7",
    "1 Kings": "PL24C87F1AB099F9E6",
    "2 Kings": "PL48C1F9D9A7C3E4E8",
    "1 Chronicles": "PLB8F9CABD9F5E7639",
    "2 Chronicles": "PL5A8D16E3B3CF4C51",
    "Ezra": "PL39DC8B7CB8B74E76",
    "Nehemiah": "PLB2E5C0C6C3B76E8D",
    "Esther": "PL88D8E7A3E9C33C92",
    "Job": "PL6D3F83FB8FE16A78",
    "Psalms": "PL47CF1A95D9C3E2FE",
    "Proverbs": "PLB4D2C3A3E1F79B5E",
    "Ecclesiastes": "PL61E7D7F5C9E7D32A",
    "Song of Solomon": "PL3E5A7D8C2F6B4E91",
    "Isaiah": "PL7E5C3D8A2F1B4E69",
    "Jeremiah": "PL9C7E5D3A8B2F1E47",
    "Lamentations": "PL2D5E7C3A8B1F4E69",
    "Ezekiel": "PL5E7C3D8A2B1F4E69",
    "Daniel": "PL8C7E5D3A2B1F4E69",
    "Hosea": "PL1E7C5D3A8B2F4E69",
    "Joel": "PL2E7C5D3A8B1F4E69",
    "Amos": "PL3E7C5D8A2B1F4E69",
    "Obadiah": "PL4E7C5D3A8B1F2E69",
    "Jonah": "PL5E7C5D3A8B1F4E69",
    "Micah": "PL6E7C5D3A8B1F4E69",
    "Nahum": "PL7E7C5D3A8B1F4E69",
    "Habakkuk": "PL8E7C5D3A8B1F4E69",
    "Zephaniah": "PL9E7C5D3A8B1F4E69",
    "Haggai": "PL0E7C5D3A8B1F4E69",
    "Zechariah": "PL1F7C5D3A8B2E4E69",
    "Malachi": "PL2F7C5D3A8B1E4E69",
    # New Testament
    "Matthew": "PLE4CE9660EAE8B8A4",
    "Mark": "PL3C9F7E5D8A2B1E46",
    "Luke": "PL4C9F7E5D8A2B1E46",
    "John": "PL5C9F7E5D8A2B1E46",
    "Acts": "PL6C9F7E5D8A2B1E46",
    "Romans": "PL7C9F7E5D8A2B1E46",
    "1 Corinthians": "PL8C9F7E5D8A2B1E46",
    "2 Corinthians": "PL9C9F7E5D8A2B1E46",
    "Galatians": "PL0C9F7E5D8A2B1E46",
    "Ephesians": "PL1D9F7E5C8A2B1E46",
    "Philippians": "PL2D9F7E5C8A2B1E46",
    "Colossians": "PL3D9F7E5C8A2B1E46",
    "1 Thessalonians": "PL4D9F7E5C8A2B1E46",
    "2 Thessalonians": "PL5D9F7E5C8A2B1E46",
    "1 Timothy": "PL6D9F7E5C8A2B1E46",
    "2 Timothy": "PL7D9F7E5C8A2B1E46",
    "Titus": "PL8D9F7E5C8A2B1E46",
    "Philemon": "PL9D9F7E5C8A2B1E46",
    "Hebrews": "PL0E9F7E5C8A2B1D46",
    "James": "PL1E9F7E5C8A2B1D46",
    "1 Peter": "PL2E9F7E5C8A2B1D46",
    "2 Peter": "PL3E9F7E5C8A2B1D46",
    "1 John": "PL4E9F7E5C8A2B1D46",
    "2 John": "PL5E9F7E5C8A2B1D46",
    "3 John": "PL6E9F7E5C8A2B1D46",
    "Jude": "PL7E9F7E5C8A2B1D46",
    "Revelation": "PL8E9F7E5C8A2B1D46"
}

# Video sync data - RITDorg YouTube channel videos
# Add video IDs from https://www.youtube.com/@RITDorg/videos
VIDEO_SYNC_DATA = {
    "Genesis_1": {
        "video_id": "GQI72THyO5I",  # Replace with actual RITDorg video ID for Genesis 1
        "playlist_id": "PL501265A092B62498",
        "playlist_index": 0,  # Chapter 1 = index 0
        "channel": "RITDorg",
        "title": "Genesis Chapter 1 - Bible Reading",
        "timestamps": [
            {"verse": 1, "start": 0, "end": 6, "words": [
                {"word": "In", "start": 0.0, "end": 0.2},
                {"word": "the", "start": 0.2, "end": 0.4},
                {"word": "beginning", "start": 0.4, "end": 1.0},
                {"word": "God", "start": 1.0, "end": 1.4},
                {"word": "created", "start": 1.4, "end": 2.0},
                {"word": "the", "start": 2.0, "end": 2.2},
                {"word": "heaven", "start": 2.2, "end": 2.8},
                {"word": "and", "start": 2.8, "end": 3.0},
                {"word": "the", "start": 3.0, "end": 3.2},
                {"word": "earth.", "start": 3.2, "end": 4.0}
            ]},
            {"verse": 2, "start": 6, "end": 18, "words": [
                {"word": "And", "start": 6.0, "end": 6.3},
                {"word": "the", "start": 6.3, "end": 6.5},
                {"word": "earth", "start": 6.5, "end": 7.0},
                {"word": "was", "start": 7.0, "end": 7.3},
                {"word": "without", "start": 7.3, "end": 7.8},
                {"word": "form,", "start": 7.8, "end": 8.3},
                {"word": "and", "start": 8.3, "end": 8.5},
                {"word": "void;", "start": 8.5, "end": 9.0},
                {"word": "and", "start": 9.0, "end": 9.3},
                {"word": "darkness", "start": 9.3, "end": 10.0},
                {"word": "was", "start": 10.0, "end": 10.3},
                {"word": "upon", "start": 10.3, "end": 10.7},
                {"word": "the", "start": 10.7, "end": 10.9},
                {"word": "face", "start": 10.9, "end": 11.3},
                {"word": "of", "start": 11.3, "end": 11.5},
                {"word": "the", "start": 11.5, "end": 11.7},
                {"word": "deep.", "start": 11.7, "end": 12.3}
            ]},
            {"verse": 3, "start": 18, "end": 24, "words": [
                {"word": "And", "start": 18.0, "end": 18.3},
                {"word": "God", "start": 18.3, "end": 18.7},
                {"word": "said,", "start": 18.7, "end": 19.2},
                {"word": "Let", "start": 19.2, "end": 19.5},
                {"word": "there", "start": 19.5, "end": 19.8},
                {"word": "be", "start": 19.8, "end": 20.0},
                {"word": "light:", "start": 20.0, "end": 20.6},
                {"word": "and", "start": 20.6, "end": 20.9},
                {"word": "there", "start": 20.9, "end": 21.2},
                {"word": "was", "start": 21.2, "end": 21.5},
                {"word": "light.", "start": 21.5, "end": 22.2}
            ]},
            {"verse": 4, "start": 24, "end": 32},
            {"verse": 5, "start": 32, "end": 42},
            {"verse": 6, "start": 42, "end": 52},
            {"verse": 7, "start": 52, "end": 65},
            {"verse": 8, "start": 65, "end": 74},
            {"verse": 9, "start": 74, "end": 86},
            {"verse": 10, "start": 86, "end": 98}
        ]
    },
    "John_1": {
        "video_id": "GQI72THyO5I",  # Replace with actual RITDorg video ID for John 1
        "playlist_id": "PL5C9F7E5D8A2B1E46",
        "playlist_index": 0,  # Chapter 1 = index 0
        "channel": "RITDorg",
        "title": "John Chapter 1 - Bible Reading",
        "timestamps": [
            {"verse": 1, "start": 0, "end": 8, "words": [
                {"word": "In", "start": 0.0, "end": 0.3},
                {"word": "the", "start": 0.3, "end": 0.5},
                {"word": "beginning", "start": 0.5, "end": 1.2},
                {"word": "was", "start": 1.2, "end": 1.5},
                {"word": "the", "start": 1.5, "end": 1.7},
                {"word": "Word,", "start": 1.7, "end": 2.2},
                {"word": "and", "start": 2.2, "end": 2.5},
                {"word": "the", "start": 2.5, "end": 2.7},
                {"word": "Word", "start": 2.7, "end": 3.1},
                {"word": "was", "start": 3.1, "end": 3.4},
                {"word": "with", "start": 3.4, "end": 3.7},
                {"word": "God,", "start": 3.7, "end": 4.2},
                {"word": "and", "start": 4.2, "end": 4.5},
                {"word": "the", "start": 4.5, "end": 4.7},
                {"word": "Word", "start": 4.7, "end": 5.1},
                {"word": "was", "start": 5.1, "end": 5.4},
                {"word": "God.", "start": 5.4, "end": 6.0}
            ]},
            {"verse": 2, "start": 8, "end": 12},
            {"verse": 3, "start": 12, "end": 20},
            {"verse": 4, "start": 20, "end": 26},
            {"verse": 5, "start": 26, "end": 32}
        ]
    },
    "Psalms_23": {
        "video_id": "GQI72THyO5I",  # Replace with actual RITDorg video ID for Psalm 23
        "playlist_id": "PL47CF1A95D9C3E2FE",
        "playlist_index": 22,  # Psalm 23 position in playlist
        "channel": "RITDorg", 
        "title": "Psalm 23 - Bible Reading",
        "timestamps": [
            {"verse": 1, "start": 0, "end": 6, "words": [
                {"word": "The", "start": 0.0, "end": 0.3},
                {"word": "LORD", "start": 0.3, "end": 0.8},
                {"word": "is", "start": 0.8, "end": 1.0},
                {"word": "my", "start": 1.0, "end": 1.3},
                {"word": "shepherd;", "start": 1.3, "end": 2.0},
                {"word": "I", "start": 2.0, "end": 2.2},
                {"word": "shall", "start": 2.2, "end": 2.5},
                {"word": "not", "start": 2.5, "end": 2.8},
                {"word": "want.", "start": 2.8, "end": 3.5}
            ]},
            {"verse": 2, "start": 6, "end": 14},
            {"verse": 3, "start": 14, "end": 22},
            {"verse": 4, "start": 22, "end": 36},
            {"verse": 5, "start": 36, "end": 48},
            {"verse": 6, "start": 48, "end": 60}
        ]
    },
    "John_3": {
        "video_id": "GQI72THyO5I",  # Replace with actual RITDorg video ID for John 3
        "playlist_id": "PL5C9F7E5D8A2B1E46",
        "playlist_index": 2,  # John 3 position in playlist
        "channel": "RITDorg",
        "title": "John Chapter 3 - Bible Reading",
        "timestamps": [
            {"verse": 16, "start": 0, "end": 15, "words": [
                {"word": "For", "start": 0.0, "end": 0.3},
                {"word": "God", "start": 0.3, "end": 0.7},
                {"word": "so", "start": 0.7, "end": 1.0},
                {"word": "loved", "start": 1.0, "end": 1.5},
                {"word": "the", "start": 1.5, "end": 1.7},
                {"word": "world,", "start": 1.7, "end": 2.3},
                {"word": "that", "start": 2.3, "end": 2.6},
                {"word": "he", "start": 2.6, "end": 2.8},
                {"word": "gave", "start": 2.8, "end": 3.2},
                {"word": "his", "start": 3.2, "end": 3.5},
                {"word": "only", "start": 3.5, "end": 3.9},
                {"word": "begotten", "start": 3.9, "end": 4.5},
                {"word": "Son,", "start": 4.5, "end": 5.0}
            ]},
            {"verse": 17, "start": 15, "end": 28}
        ]
    },
    "Matthew_1": {
        "video_id": "g-IFb0O7J5A",
        "playlist_id": "PLE4CE9660EAE8B8A4",
        "playlist_index": 0,  # Chapter 1 = index 0
        "channel": "RITDorg",
        "title": "Matthew Chapter 1 - Bible Reading",
        "timestamps": [
            {"verse": 1, "start": 0, "end": 8, "words": [
                {"word": "The", "start": 0.0, "end": 0.3},
                {"word": "book", "start": 0.3, "end": 0.6},
                {"word": "of", "start": 0.6, "end": 0.8},
                {"word": "the", "start": 0.8, "end": 1.0},
                {"word": "generation", "start": 1.0, "end": 1.8},
                {"word": "of", "start": 1.8, "end": 2.0},
                {"word": "Jesus", "start": 2.0, "end": 2.5},
                {"word": "Christ,", "start": 2.5, "end": 3.2},
                {"word": "the", "start": 3.2, "end": 3.4},
                {"word": "son", "start": 3.4, "end": 3.7},
                {"word": "of", "start": 3.7, "end": 3.9},
                {"word": "David,", "start": 3.9, "end": 4.4},
                {"word": "the", "start": 4.4, "end": 4.6},
                {"word": "son", "start": 4.6, "end": 4.9},
                {"word": "of", "start": 4.9, "end": 5.1},
                {"word": "Abraham.", "start": 5.1, "end": 6.0}
            ]},
            {"verse": 2, "start": 8, "end": 16},
            {"verse": 3, "start": 16, "end": 24},
            {"verse": 4, "start": 24, "end": 32},
            {"verse": 5, "start": 32, "end": 42},
            {"verse": 6, "start": 42, "end": 54},
            {"verse": 7, "start": 54, "end": 62},
            {"verse": 8, "start": 62, "end": 70},
            {"verse": 9, "start": 70, "end": 78},
            {"verse": 10, "start": 78, "end": 86},
            {"verse": 11, "start": 86, "end": 98},
            {"verse": 12, "start": 98, "end": 110},
            {"verse": 13, "start": 110, "end": 120},
            {"verse": 14, "start": 120, "end": 130},
            {"verse": 15, "start": 130, "end": 140},
            {"verse": 16, "start": 140, "end": 156},
            {"verse": 17, "start": 156, "end": 180},
            {"verse": 18, "start": 180, "end": 210, "words": [
                {"word": "Now", "start": 180.0, "end": 180.4},
                {"word": "the", "start": 180.4, "end": 180.6},
                {"word": "birth", "start": 180.6, "end": 181.0},
                {"word": "of", "start": 181.0, "end": 181.2},
                {"word": "Jesus", "start": 181.2, "end": 181.7},
                {"word": "Christ", "start": 181.7, "end": 182.2},
                {"word": "was", "start": 182.2, "end": 182.5},
                {"word": "on", "start": 182.5, "end": 182.7},
                {"word": "this", "start": 182.7, "end": 183.0},
                {"word": "wise:", "start": 183.0, "end": 183.5}
            ]},
            {"verse": 19, "start": 210, "end": 235},
            {"verse": 20, "start": 235, "end": 275},
            {"verse": 21, "start": 275, "end": 300, "words": [
                {"word": "And", "start": 275.0, "end": 275.3},
                {"word": "she", "start": 275.3, "end": 275.6},
                {"word": "shall", "start": 275.6, "end": 276.0},
                {"word": "bring", "start": 276.0, "end": 276.4},
                {"word": "forth", "start": 276.4, "end": 276.8},
                {"word": "a", "start": 276.8, "end": 277.0},
                {"word": "son,", "start": 277.0, "end": 277.5},
                {"word": "and", "start": 277.5, "end": 277.8},
                {"word": "thou", "start": 277.8, "end": 278.1},
                {"word": "shalt", "start": 278.1, "end": 278.5},
                {"word": "call", "start": 278.5, "end": 278.8},
                {"word": "his", "start": 278.8, "end": 279.1},
                {"word": "name", "start": 279.1, "end": 279.5},
                {"word": "JESUS:", "start": 279.5, "end": 280.2}
            ]},
            {"verse": 22, "start": 300, "end": 320},
            {"verse": 23, "start": 320, "end": 355, "words": [
                {"word": "Behold,", "start": 320.0, "end": 320.6},
                {"word": "a", "start": 320.6, "end": 320.8},
                {"word": "virgin", "start": 320.8, "end": 321.3},
                {"word": "shall", "start": 321.3, "end": 321.7},
                {"word": "be", "start": 321.7, "end": 322.0},
                {"word": "with", "start": 322.0, "end": 322.3},
                {"word": "child,", "start": 322.3, "end": 322.9}
            ]},
            {"verse": 24, "start": 355, "end": 380},
            {"verse": 25, "start": 380, "end": 410}
        ]
    },
    "Matthew_2": {
        "video_id": "BcABGR5L6uU",
        "playlist_id": "PLE4CE9660EAE8B8A4",
        "playlist_index": 1,  # Chapter 2 = index 1
        "channel": "RITDorg",
        "title": "Matthew Chapter 2 - Bible Reading",
        "timestamps": [
            {"verse": 1, "start": 0, "end": 12},
            {"verse": 2, "start": 12, "end": 24},
            {"verse": 3, "start": 24, "end": 32},
            {"verse": 4, "start": 32, "end": 42},
            {"verse": 5, "start": 42, "end": 52},
            {"verse": 6, "start": 52, "end": 68},
            {"verse": 7, "start": 68, "end": 78},
            {"verse": 8, "start": 78, "end": 94},
            {"verse": 9, "start": 94, "end": 112},
            {"verse": 10, "start": 112, "end": 120},
            {"verse": 11, "start": 120, "end": 142},
            {"verse": 12, "start": 142, "end": 156},
            {"verse": 13, "start": 156, "end": 178},
            {"verse": 14, "start": 178, "end": 190},
            {"verse": 15, "start": 190, "end": 210},
            {"verse": 16, "start": 210, "end": 240},
            {"verse": 17, "start": 240, "end": 252},
            {"verse": 18, "start": 252, "end": 275},
            {"verse": 19, "start": 275, "end": 292},
            {"verse": 20, "start": 292, "end": 312},
            {"verse": 21, "start": 312, "end": 326},
            {"verse": 22, "start": 326, "end": 350},
            {"verse": 23, "start": 350, "end": 375}
        ]
    },
    "Matthew_3": {
        "video_id": "VBx6V1iaHFk",
        "playlist_id": "PLE4CE9660EAE8B8A4",
        "playlist_index": 2,  # Chapter 3 = index 2
        "channel": "RITDorg",
        "title": "Matthew Chapter 3 - Bible Reading",
        "timestamps": [
            {"verse": 1, "start": 0, "end": 12},
            {"verse": 2, "start": 12, "end": 22},
            {"verse": 3, "start": 22, "end": 40},
            {"verse": 4, "start": 40, "end": 55},
            {"verse": 5, "start": 55, "end": 68},
            {"verse": 6, "start": 68, "end": 80},
            {"verse": 7, "start": 80, "end": 100},
            {"verse": 8, "start": 100, "end": 112},
            {"verse": 9, "start": 112, "end": 128},
            {"verse": 10, "start": 128, "end": 145},
            {"verse": 11, "start": 145, "end": 170},
            {"verse": 12, "start": 170, "end": 195},
            {"verse": 13, "start": 195, "end": 210},
            {"verse": 14, "start": 210, "end": 225},
            {"verse": 15, "start": 225, "end": 248},
            {"verse": 16, "start": 248, "end": 275},
            {"verse": 17, "start": 275, "end": 300}
        ]
    },
    "Matthew_4": {
        "video_id": "3DC_MXg8fkM",
        "playlist_id": "PLE4CE9660EAE8B8A4",
        "playlist_index": 3,
        "channel": "RITDorg",
        "title": "Matthew Chapter 4 - Bible Reading",
        "timestamps": [
            {"verse": 1, "start": 0, "end": 15},
            {"verse": 2, "start": 15, "end": 35},
            {"verse": 3, "start": 35, "end": 50},
            {"verse": 4, "start": 50, "end": 65},
            {"verse": 5, "start": 65, "end": 85},
            {"verse": 6, "start": 85, "end": 105},
            {"verse": 7, "start": 105, "end": 125},
            {"verse": 8, "start": 125, "end": 150},
            {"verse": 9, "start": 150, "end": 175},
            {"verse": 10, "start": 175, "end": 195},
            {"verse": 11, "start": 195, "end": 220},
            {"verse": 12, "start": 220, "end": 240},
            {"verse": 13, "start": 240, "end": 265},
            {"verse": 14, "start": 265, "end": 285},
            {"verse": 15, "start": 285, "end": 310},
            {"verse": 16, "start": 310, "end": 330},
            {"verse": 17, "start": 330, "end": 350},
            {"verse": 18, "start": 350, "end": 375},
            {"verse": 19, "start": 375, "end": 400},
            {"verse": 20, "start": 400, "end": 420},
            {"verse": 21, "start": 420, "end": 445},
            {"verse": 22, "start": 445, "end": 470},
            {"verse": 23, "start": 470, "end": 495},
            {"verse": 24, "start": 495, "end": 520},
            {"verse": 25, "start": 520, "end": 550}
        ]
    },
    "Matthew_5": {
        "video_id": "placeholder_video_id",
        "playlist_id": "PLE4CE9660EAE8B8A4",
        "playlist_index": 4,
        "channel": "RITDorg",
        "title": "Matthew Chapter 5 - Bible Reading",
        "timestamps": [
            {"verse": 1, "start": 0, "end": 20},
            {"verse": 2, "start": 20, "end": 35},
            {"verse": 3, "start": 35, "end": 45},
            {"verse": 4, "start": 45, "end": 55},
            {"verse": 5, "start": 55, "end": 70},
            {"verse": 6, "start": 70, "end": 85},
            {"verse": 7, "start": 85, "end": 95},
            {"verse": 8, "start": 95, "end": 110},
            {"verse": 9, "start": 110, "end": 125},
            {"verse": 10, "start": 125, "end": 145},
            {"verse": 11, "start": 145, "end": 170},
            {"verse": 12, "start": 170, "end": 190},
            {"verse": 13, "start": 190, "end": 215},
            {"verse": 14, "start": 215, "end": 235},
            {"verse": 15, "start": 235, "end": 255},
            {"verse": 16, "start": 255, "end": 275},
            {"verse": 17, "start": 275, "end": 300},
            {"verse": 18, "start": 300, "end": 325},
            {"verse": 19, "start": 325, "end": 350},
            {"verse": 20, "start": 350, "end": 370},
            {"verse": 21, "start": 370, "end": 390},
            {"verse": 22, "start": 390, "end": 420},
            {"verse": 23, "start": 420, "end": 445},
            {"verse": 24, "start": 445, "end": 465},
            {"verse": 25, "start": 465, "end": 490},
            {"verse": 26, "start": 490, "end": 510},
            {"verse": 27, "start": 510, "end": 525},
            {"verse": 28, "start": 525, "end": 545},
            {"verse": 29, "start": 545, "end": 565},
            {"verse": 30, "start": 565, "end": 585},
            {"verse": 31, "start": 585, "end": 605},
            {"verse": 32, "start": 605, "end": 635},
            {"verse": 33, "start": 635, "end": 655},
            {"verse": 34, "start": 655, "end": 675},
            {"verse": 35, "start": 675, "end": 690},
            {"verse": 36, "start": 690, "end": 710},
            {"verse": 37, "start": 710, "end": 725},
            {"verse": 38, "start": 725, "end": 740},
            {"verse": 39, "start": 740, "end": 760},
            {"verse": 40, "start": 760, "end": 775},
            {"verse": 41, "start": 775, "end": 790},
            {"verse": 42, "start": 790, "end": 805},
            {"verse": 43, "start": 805, "end": 820},
            {"verse": 44, "start": 820, "end": 840},
            {"verse": 45, "start": 840, "end": 865},
            {"verse": 46, "start": 865, "end": 885},
            {"verse": 47, "start": 885, "end": 905},
            {"verse": 48, "start": 905, "end": 925}
        ]
    },
    "Matthew_6": {
        "video_id": "placeholder_video_id",
        "playlist_id": "PLE4CE9660EAE8B8A4",
        "playlist_index": 5,
        "channel": "RITDorg",
        "title": "Matthew Chapter 6 - Bible Reading",
        "timestamps": [
            {"verse": 1, "start": 0, "end": 20},
            {"verse": 2, "start": 20, "end": 45},
            {"verse": 3, "start": 45, "end": 60},
            {"verse": 4, "start": 60, "end": 75},
            {"verse": 5, "start": 75, "end": 100},
            {"verse": 6, "start": 100, "end": 115},
            {"verse": 7, "start": 115, "end": 130},
            {"verse": 8, "start": 130, "end": 145},
            {"verse": 9, "start": 145, "end": 165},
            {"verse": 10, "start": 165, "end": 180},
            {"verse": 11, "start": 180, "end": 190},
            {"verse": 12, "start": 190, "end": 205},
            {"verse": 13, "start": 205, "end": 220},
            {"verse": 14, "start": 220, "end": 235},
            {"verse": 15, "start": 235, "end": 250},
            {"verse": 16, "start": 250, "end": 275},
            {"verse": 17, "start": 275, "end": 290},
            {"verse": 18, "start": 290, "end": 305},
            {"verse": 19, "start": 305, "end": 325},
            {"verse": 20, "start": 325, "end": 340},
            {"verse": 21, "start": 340, "end": 355},
            {"verse": 22, "start": 355, "end": 375},
            {"verse": 23, "start": 375, "end": 395},
            {"verse": 24, "start": 395, "end": 420},
            {"verse": 25, "start": 420, "end": 445},
            {"verse": 26, "start": 445, "end": 465},
            {"verse": 27, "start": 465, "end": 480},
            {"verse": 28, "start": 480, "end": 500},
            {"verse": 29, "start": 500, "end": 520},
            {"verse": 30, "start": 520, "end": 545},
            {"verse": 31, "start": 545, "end": 565},
            {"verse": 32, "start": 565, "end": 585},
            {"verse": 33, "start": 585, "end": 605},
            {"verse": 34, "start": 605, "end": 625}
        ]
    },
    "Matthew_7": {
        "video_id": "placeholder_video_id",
        "playlist_id": "PLE4CE9660EAE8B8A4",
        "playlist_index": 6,
        "channel": "RITDorg",
        "title": "Matthew Chapter 7 - Bible Reading",
        "timestamps": [
            {"verse": 1, "start": 0, "end": 10},
            {"verse": 2, "start": 10, "end": 25},
            {"verse": 3, "start": 25, "end": 45},
            {"verse": 4, "start": 45, "end": 65},
            {"verse": 5, "start": 65, "end": 85},
            {"verse": 6, "start": 85, "end": 105},
            {"verse": 7, "start": 105, "end": 120},
            {"verse": 8, "start": 120, "end": 135},
            {"verse": 9, "start": 135, "end": 150},
            {"verse": 10, "start": 150, "end": 165},
            {"verse": 11, "start": 165, "end": 185},
            {"verse": 12, "start": 185, "end": 205},
            {"verse": 13, "start": 205, "end": 225},
            {"verse": 14, "start": 225, "end": 240},
            {"verse": 15, "start": 240, "end": 260},
            {"verse": 16, "start": 260, "end": 275},
            {"verse": 17, "start": 275, "end": 290},
            {"verse": 18, "start": 290, "end": 305},
            {"verse": 19, "start": 305, "end": 320},
            {"verse": 20, "start": 320, "end": 335},
            {"verse": 21, "start": 335, "end": 355},
            {"verse": 22, "start": 355, "end": 380},
            {"verse": 23, "start": 380, "end": 400},
            {"verse": 24, "start": 400, "end": 425},
            {"verse": 25, "start": 425, "end": 445},
            {"verse": 26, "start": 445, "end": 470},
            {"verse": 27, "start": 470, "end": 490},
            {"verse": 28, "start": 490, "end": 510},
            {"verse": 29, "start": 510, "end": 530}
        ]
    },
    "Matthew_8": {
        "video_id": "placeholder_video_id",
        "playlist_id": "PLE4CE9660EAE8B8A4",
        "playlist_index": 7,
        "channel": "RITDorg",
        "title": "Matthew Chapter 8 - Bible Reading",
        "timestamps": [
            {"verse": 1, "start": 0, "end": 12},
            {"verse": 2, "start": 12, "end": 28},
            {"verse": 3, "start": 28, "end": 45},
            {"verse": 4, "start": 45, "end": 70},
            {"verse": 5, "start": 70, "end": 85},
            {"verse": 6, "start": 85, "end": 95},
            {"verse": 7, "start": 95, "end": 105},
            {"verse": 8, "start": 105, "end": 125},
            {"verse": 9, "start": 125, "end": 150},
            {"verse": 10, "start": 150, "end": 170},
            {"verse": 11, "start": 170, "end": 190},
            {"verse": 12, "start": 190, "end": 205},
            {"verse": 13, "start": 205, "end": 220},
            {"verse": 14, "start": 220, "end": 235},
            {"verse": 15, "start": 235, "end": 245},
            {"verse": 16, "start": 245, "end": 265},
            {"verse": 17, "start": 265, "end": 285},
            {"verse": 18, "start": 285, "end": 300},
            {"verse": 19, "start": 300, "end": 315},
            {"verse": 20, "start": 315, "end": 335},
            {"verse": 21, "start": 335, "end": 350},
            {"verse": 22, "start": 350, "end": 365},
            {"verse": 23, "start": 365, "end": 375},
            {"verse": 24, "start": 375, "end": 395},
            {"verse": 25, "start": 395, "end": 410},
            {"verse": 26, "start": 410, "end": 425},
            {"verse": 27, "start": 425, "end": 440},
            {"verse": 28, "start": 440, "end": 465},
            {"verse": 29, "start": 465, "end": 480},
            {"verse": 30, "start": 480, "end": 490},
            {"verse": 31, "start": 490, "end": 505},
            {"verse": 32, "start": 505, "end": 525},
            {"verse": 33, "start": 525, "end": 545},
            {"verse": 34, "start": 545, "end": 565}
        ]
    }
}

# Books to exclude from the dropdown (not fully implemented yet)
EXCLUDED_BOOKS = {'Genesis', 'Psalms'}

@app.route('/')
def index():
    books = [b for b in BIBLE_DATA.keys() if b not in EXCLUDED_BOOKS]
    return render_template('index.html', books=books, translations=TRANSLATIONS)

@app.route('/api/books')
def get_books():
    return jsonify([b for b in BIBLE_DATA.keys() if b not in EXCLUDED_BOOKS])

@app.route('/api/translations')
def get_translations():
    return jsonify(TRANSLATIONS)

@app.route('/api/chapters/<book>')
def get_chapters(book):
    if book in BIBLE_DATA:
        return jsonify(list(BIBLE_DATA[book].keys()))
    return jsonify([])

@app.route('/api/verses/<book>/<int:chapter>')
def get_verses(book, chapter):
    translation = request.args.get('translation', 'NIV')
    bible = BIBLE_TRANSLATIONS.get(translation, BIBLE_NIV)
    
    if book in bible and chapter in bible[book]:
        verses = bible[book][chapter]
        return jsonify({"verses": verses, "translation": translation, "fallback": False})
    # Fallback to NIV if translation doesn't have the passage
    if book in BIBLE_KJV and chapter in BIBLE_KJV[book]:
        return jsonify({"verses": BIBLE_KJV[book][chapter], "translation": "KJV", "fallback": True, "requested": translation})
    return jsonify({"verses": {}, "translation": translation, "fallback": False})

@app.route('/api/verses/parallel/<book>/<int:chapter>')
def get_parallel_verses(book, chapter):
    """Get verses in two translations side by side"""
    trans1 = request.args.get('translation1', 'NIV')
    trans2 = request.args.get('translation2', 'HEBREW')
    
    bible1 = BIBLE_TRANSLATIONS.get(trans1, BIBLE_NIV)
    bible2 = BIBLE_TRANSLATIONS.get(trans2, BIBLE_HEBREW)
    
    verses1 = {}
    verses2 = {}
    fallback1 = False
    fallback2 = False
    actual_trans1 = trans1
    actual_trans2 = trans2
    
    if book in bible1 and chapter in bible1[book]:
        verses1 = bible1[book][chapter]
    elif book in BIBLE_NIV and chapter in BIBLE_NIV[book]:
        verses1 = BIBLE_NIV[book][chapter]
        fallback1 = True
        actual_trans1 = "NIV"
        
    if book in bible2 and chapter in bible2[book]:
        verses2 = bible2[book][chapter]
    elif book in BIBLE_HEBREW and chapter in BIBLE_HEBREW[book]:
        verses2 = BIBLE_HEBREW[book][chapter]
        fallback2 = True
        actual_trans2 = "HEBREW"
    
    return jsonify({
        "translation1": {"name": trans1, "actual": actual_trans1, "verses": verses1, "fallback": fallback1},
        "translation2": {"name": trans2, "actual": actual_trans2, "verses": verses2, "fallback": fallback2}
    })

@app.route('/api/sync/<book>/<int:chapter>')
def get_sync_data(book, chapter):
    """Get video sync data for a chapter, supporting playlists"""
    key = f"{book}_{chapter}"
    
    # Check if we have specific sync data for this chapter
    if key in VIDEO_SYNC_DATA:
        return jsonify(VIDEO_SYNC_DATA[key])
    
    # If no specific data, try to provide playlist-based data
    if book in RITDORG_PLAYLISTS:
        return jsonify({
            "video_id": None,
            "playlist_id": RITDORG_PLAYLISTS[book],
            "playlist_index": chapter - 1,  # Chapters are 1-indexed, playlist is 0-indexed
            "channel": "RITDorg",
            "title": f"{book} Chapter {chapter} - Bible Reading",
            "timestamps": []  # No word-level sync, but video will still play
        })
    
    return jsonify({"video_id": None, "playlist_id": None, "timestamps": [], "channel": "RITDorg"})

@app.route('/api/playlists')
def get_playlists():
    """Get all RITDorg playlists"""
    return jsonify(RITDORG_PLAYLISTS)

@app.route('/api/playlists/<book>')
def get_playlist_for_book(book):
    """Get the RITDorg playlist for a specific book"""
    if book in RITDORG_PLAYLISTS:
        return jsonify({
            "book": book,
            "playlist_id": RITDORG_PLAYLISTS[book],
            "playlist_url": f"https://www.youtube.com/playlist?list={RITDORG_PLAYLISTS[book]}"
        })
    return jsonify({"error": f"No playlist found for {book}"}), 404

@app.route('/api/captions/<video_id>')
def get_video_captions(video_id):
    """Fetch captions/subtitles from a YouTube video for dynamic sync"""
    try:
        transcript_list = ytt_api.list(video_id)
        
        # Try to find a transcript
        transcript = None
        transcript_language = None
        
        # Priority 1: Try manually created English transcripts
        english_langs = ['en', 'en-US', 'en-GB']
        try:
            for lang in english_langs:
                try:
                    transcript = transcript_list.find_manually_created_transcript([lang])
                    transcript_language = lang
                    break
                except:
                    continue
        except:
            pass
        
        # Priority 2: Try auto-generated English
        if not transcript:
            try:
                for lang in english_langs:
                    try:
                        transcript = transcript_list.find_generated_transcript([lang])
                        transcript_language = lang
                        break
                    except:
                        continue
            except:
                pass
        
        # Priority 3: Try to translate any available transcript to English
        if not transcript:
            try:
                available = list(transcript_list)
                for t in available:
                    if t.is_translatable:
                        try:
                            transcript = t.translate('en')
                            transcript_language = 'en (translated from ' + t.language_code + ')'
                            break
                        except:
                            continue
            except:
                pass
        
        # Priority 4: Fall back to any available transcript
        if not transcript:
            try:
                available = list(transcript_list)
                if available:
                    transcript = available[0]
                    transcript_language = transcript.language_code
            except:
                pass
        
        if transcript:
            # Fetch the actual transcript data
            captions = transcript.fetch()
            
            # Format for our sync system
            formatted_captions = []
            for caption in captions:
                # New API uses object attributes instead of dict keys
                start = caption.start
                duration = caption.duration
                text = caption.text
                end = start + duration
                
                # Split text into words and calculate word timings
                words = text.split()
                word_timings = []
                if words:
                    word_duration = duration / len(words)
                    for i, word in enumerate(words):
                        word_start = start + (i * word_duration)
                        word_end = word_start + word_duration
                        word_timings.append({
                            "text": word,
                            "start": word_start,
                            "end": word_end
                        })
                
                formatted_captions.append({
                    "text": text,
                    "start": start,
                    "duration": duration,
                    "end": end,
                    "words": word_timings
                })
            
            return jsonify({
                "video_id": video_id,
                "language": transcript_language,
                "is_generated": transcript.is_generated,
                "captions": formatted_captions,
                "success": True
            })
        else:
            return jsonify({
                "video_id": video_id,
                "error": "No captions available for this video",
                "success": False
            })
            
    except Exception as e:
        return jsonify({
            "video_id": video_id,
            "error": str(e),
            "success": False
        })

@app.route('/api/captions/<video_id>/languages')
def get_caption_languages(video_id):
    """Get available caption languages for a video"""
    try:
        transcript_list = ytt_api.list(video_id)
        
        languages = []
        for transcript in transcript_list:
            languages.append({
                "code": transcript.language_code,
                "name": transcript.language,
                "is_generated": transcript.is_generated,
                "is_translatable": transcript.is_translatable
            })
        
        return jsonify({
            "video_id": video_id,
            "languages": languages,
            "success": True
        })
    except Exception as e:
        return jsonify({
            "video_id": video_id,
            "error": str(e),
            "success": False
        })

if __name__ == '__main__':
    app.run(debug=False, port=8000, host='0.0.0.0')
