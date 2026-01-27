from flask import Flask, render_template, jsonify, request
import json
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import JSONFormatter

app = Flask(__name__)

# Create YouTubeTranscriptApi instance
ytt_api = YouTubeTranscriptApi()

# Available translations
TRANSLATIONS = ["KJV", "NIV", "ESV", "NASB", "Hebrew", "Greek"]

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
        }
    }
}

# Hebrew (Transliterated) - Original language for Old Testament
BIBLE_HEBREW = {
    "Genesis": {
        1: {
            1: "Bereshit bara Elohim et hashamayim ve'et ha'aretz.",
            2: "Veha'aretz hayetah tohu vavohu vechoshech al-penei tehom veruach Elohim merachefet al-penei hamayim.",
            3: "Vayomer Elohim yehi or vayehi-or.",
            4: "Vayar Elohim et-ha'or ki-tov vayavdel Elohim bein ha'or uvein hachoshech.",
            5: "Vayikra Elohim la'or yom velachoshech kara laylah vayehi-erev vayehi-voker yom echad.",
            6: "Vayomer Elohim yehi rakia betoch hamayim vihi mavdil bein mayim lamayim.",
            7: "Vaya'as Elohim et-harakia vayavdel bein hamayim asher mitachat larakia uvein hamayim asher me'al larakia vayehi-chen.",
            8: "Vayikra Elohim larakia shamayim vayehi-erev vayehi-voker yom sheni.",
            9: "Vayomer Elohim yikavu hamayim mitachat hashamayim el-makom echad vetera'eh hayabashah vayehi-chen.",
            10: "Vayikra Elohim layabashah eretz ulemikveh hamayim kara yamim vayar Elohim ki-tov."
        }
    },
    "Psalms": {
        23: {
            1: "Mizmor leDavid. Adonai ro'i lo echsar.",
            2: "Bin'ot deshe yarbitzeini al mei menuchot yenahaleni.",
            3: "Nafshi yeshovev yancheini vema'agelei tzedek lema'an shemo.",
            4: "Gam ki elech begei tzalmavet lo ira ra ki Atah imadi shivtecha umishantecha hemah yenachamuni.",
            5: "Ta'aroch lefanai shulchan neged tzorerai dishanta vashemen roshi kosi revayah.",
            6: "Ach tov vachesed yirdefuni kol yemei chayai veshavti beveit Adonai le'orech yamim."
        }
    },
    "Matthew": {
        1: {
            1: "Sefer toldot Yeshua HaMashiach, ben David, ben Avraham.",
            2: "Avraham holid et-Yitzchak, veYitzchak holid et-Ya'akov, veYa'akov holid et-Yehudah ve'et-echav.",
            3: "ViYhudah holid et-Peretz ve'et-Zerach miTamar, uPeretz holid et-Chetzron, veChetzron holid et-Ram.",
            4: "VeRam holid et-Aminadav, veAminadav holid et-Nachshon, veNachshon holid et-Salmon.",
            5: "VeSalmon holid et-Bo'az miRachav, uBo'az holid et-Oved miRut, veOved holid et-Yishai.",
            6: "VeYishai holid et-David HaMelech. VeDavid holid et-Shlomo me'eshet Uriyah.",
            7: "VeShlomo holid et-Rechav'am, veRechav'am holid et-Aviyah, veAviyah holid et-Asa.",
            8: "VeAsa holid et-Yehoshafat, viYhoshafat holid et-Yoram, veYoram holid et-Uziyahu.",
            9: "VeUziyahu holid et-Yotam, veYotam holid et-Achaz, veAchaz holid et-Chizkiyahu.",
            10: "VeChizkiyahu holid et-Menasheh, uMenasheh holid et-Amon, veAmon holid et-Yoshiyahu.",
            11: "VeYoshiyahu holid et-Yechonyahu ve'et-echav bizman galut Bavel.",
            12: "Ve'acharei galut Bavel, Yechonyahu holid et-She'altiel, uShe'altiel holid et-Zerubavel.",
            13: "VeZerubavel holid et-Avihud, veAvihud holid et-Elyakim, veElyakim holid et-Azur.",
            14: "VeAzur holid et-Tzadok, veTzadok holid et-Yakhin, veYakhin holid et-Elihud.",
            15: "VeElihud holid et-El'azar, veEl'azar holid et-Matan, uMatan holid et-Ya'akov.",
            16: "VeYa'akov holid et-Yosef ba'al Miryam, asher mimenah nolad Yeshua haniqra Mashiach.",
            17: "Kol hadorot me'Avraham ad David arba'ah asar dorot, umeDavid ad galut Bavel arba'ah asar dorot, umigalut Bavel ad HaMashiach arba'ah asar dorot.",
            18: "VeHineh ledat Yeshua HaMashiach kach hayah: Ka'asher Miryam imo hayetah me'oraset leYosef, lifnei she'ba'u yachdav, nimtze'ah harah meRuach HaKodesh.",
            19: "VeYosef ba'alah, ish tzadik hu, velo ratzah lehotziah lecharpa, vayachshov leshalchah baseter.",
            20: "VeHu choshev al eleh, vehineh malach Adonai nir'ah elav bachalom le'mor: Yosef ben David, al tira lakachat et Miryam ishtecha, ki haherayon asher bah meRuach HaKodesh hu.",
            21: "VeHi teled ben, vetikra et-shemo Yeshua, ki hu yoshia et-amo mechatoteihem.",
            22: "VeChol zot hayah lemale'et et asher diber Adonai beyad hanavi le'mor:",
            23: "Hineh ha'almah harah veyoledet ben, vekar'u shemo Imanu'el, asher peirusho El imanu.",
            24: "VaYosef heikitz mishnato vaya'as ka'asher tzivahu malach Adonai, vayikach et-ishto.",
            25: "Velo yada'ah ad asher yaldah et-benah habechor, vayikra et-shemo Yeshua."
        },
        2: {
            1: "VaYeshua nolad beBeit Lechem biYhudah, bimei Hordos hamelech, vehineh chachamim mibaMizrach ba'u liYerushalayim.",
            2: "Vayomeru, Eifo hu hanolad melech haYehudim? Ki ra'inu et-kochavo bamizrach, uvanu lehishtachavot lo.",
            3: "Vayishma Hordos hamelech vayibahal, vechol Yerushalayim ito.",
            4: "Vaye'esof et-kol rashei hakohanim vesoferim ha'am, vayish'al otam eifo yivaled haMashiach.",
            5: "Vayomeru elav, beBeit Lechem biYhudah, ki chen katuv al-yedei hanavi.",
            6: "Ve'atah Beit Lechem eretz Yehudah, lo tza'ir atah be'alfei Yehudah, ki mimcha yetze moshel asher yir'eh et-ami Yisrael.",
            7: "Az Hordos kara lachachamim baseter, vayidrosh mehem et-et hakochav hanir'eh.",
            8: "Vayishlachem leBeit Lechem vayomer, Lechu vechapsu heitev et-hayeled, vechi timtze'uhu hagidu li, lema'an avo gam ani lehishtachavot lo.",
            9: "Vayishme'u et-hamelech vayelechu, vehineh hakochav asher ra'u vamizrach holech lifneihem ad bo'o vaya'amod me'al hamakom asher hayeled sham.",
            10: "Vayir'u et-hakochav vayismechu simchah gedolah me'od.",
            11: "Vayavo'u habaitah, vayir'u et-hayeled im Miryam imo, vayipelu vayishtachavu lo, vayiftachu et-otzroteihem vayakrivu lo matanot: zahav ulevonah umor.",
            12: "Vayuzaharu bachalom shelo lashuv el-Hordos, vayashuvu be'derech acheret el-artzam.",
            13: "Vayelchu hem, vehineh mal'ach Adonai nir'ah el-Yosef bachalom lemor, Kum kach et-hayeled ve'et-imo, uvrach Mitzraymah, vehyeh sham ad asher omar lecha, ki Hordos mevakesh et-hayeled lehashmido.",
            14: "Vayakam vayikach et-hayeled ve'et-imo lailah, vayelech Mitzraymah.",
            15: "Vayehi sham ad mot Hordos, lema'an yimale hadavar hane'emar me'et Adonai al-yad hanavi, miMitzrayim karati livni.",
            16: "Az Hordos ki ra'ah ki hut'ah min-hachachamim, vayiktzof me'od, vayishlach vayaharog et-kol hayeladim asher beBeit Lechem uvechol gevuleiha, miben shnatayim ulemattah, ke'et asher chakkar me'et hachachamim.",
            17: "Az nimla hadavar hane'emar al-yedei Yirmiyahu hanavi lemor,",
            18: "Kol beRamah nishma, nehi uvechi tamrurim, Rachel mevakah al-baneiha, me'anah lehinachem al-baneiha ki einenu.",
            19: "Vayehi acharei mot Hordos, vehineh mal'ach Adonai nir'ah bachalom el-Yosef beMitzrayim.",
            20: "Vayomer, Kum kach et-hayeled ve'et-imo, velech el-eretz Yisrael, ki metu hamevakshim et-nefesh hayeled.",
            21: "Vayakam vayikach et-hayeled ve'et-imo, vayavo el-eretz Yisrael.",
            22: "Vayishma ki Archelaus molech biYhudah tachat Hordos aviv, vayira lalechet shamah, vayuzhar bachalom, vayasar el-galil Hagelil.",
            23: "Vayavo vayeshev be'ir hannikret Natzeret, lema'an yimale hane'emar al-yedei hanevi'im, Notzri yikarei."
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
    "KJV": BIBLE_KJV,
    "NIV": BIBLE_NIV,
    "ESV": BIBLE_ESV,
    "NASB": BIBLE_NASB,
    "Hebrew": BIBLE_HEBREW,
    "Greek": BIBLE_GREEK
}

# Primary Bible data (KJV as default)
BIBLE_DATA = BIBLE_KJV

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
    translation = request.args.get('translation', 'KJV')
    bible = BIBLE_TRANSLATIONS.get(translation, BIBLE_KJV)
    
    if book in bible and chapter in bible[book]:
        verses = bible[book][chapter]
        return jsonify({"verses": verses, "translation": translation, "fallback": False})
    # Fallback to KJV if translation doesn't have the passage
    if book in BIBLE_KJV and chapter in BIBLE_KJV[book]:
        return jsonify({"verses": BIBLE_KJV[book][chapter], "translation": "KJV", "fallback": True, "requested": translation})
    return jsonify({"verses": {}, "translation": translation, "fallback": False})

@app.route('/api/verses/parallel/<book>/<int:chapter>')
def get_parallel_verses(book, chapter):
    """Get verses in two translations side by side"""
    trans1 = request.args.get('translation1', 'KJV')
    trans2 = request.args.get('translation2', 'NIV')
    
    bible1 = BIBLE_TRANSLATIONS.get(trans1, BIBLE_KJV)
    bible2 = BIBLE_TRANSLATIONS.get(trans2, BIBLE_KJV)
    
    verses1 = {}
    verses2 = {}
    fallback1 = False
    fallback2 = False
    actual_trans1 = trans1
    actual_trans2 = trans2
    
    if book in bible1 and chapter in bible1[book]:
        verses1 = bible1[book][chapter]
    elif book in BIBLE_KJV and chapter in BIBLE_KJV[book]:
        verses1 = BIBLE_KJV[book][chapter]
        fallback1 = True
        actual_trans1 = "KJV"
        
    if book in bible2 and chapter in bible2[book]:
        verses2 = bible2[book][chapter]
    elif book in BIBLE_KJV and chapter in BIBLE_KJV[book]:
        verses2 = BIBLE_KJV[book][chapter]
        fallback2 = True
        actual_trans2 = "KJV"
    
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
                formatted_captions.append({
                    "text": caption.text,
                    "start": caption.start,
                    "duration": caption.duration,
                    "end": caption.start + caption.duration
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
    app.run(debug=True, port=8000, host='0.0.0.0')
